"""Handler for finding the best matching entity using LLM."""

import json
from typing import Any, Dict
from ....shared.mcp_server import ToolResult
from ....shared.neo4j_service import Neo4jService
from ....shared.logger import get_logger
import httpx
import os

logger = get_logger(__name__)


async def find_best_entity_handler(
    neo4j_service: Neo4jService,
    query: str,
    top_k: int = 50
) -> ToolResult:
    """
    Find the best matching entity using LLM disambiguation.
    
    1. Get ALL entities from Neo4j (Module, Class, Function, etc.)
    2. Use LLM to find the most suitable entity for the query
    3. Return the best match with its relationships
    """
    try:
        logger.info(f"🔍 find_best_entity_handler called")
        logger.info(f"   📝 Query: {query[:80]}...")
        
        # STEP 1: Get all entities from Neo4j
        logger.info(f"\n📊 STEP 1: Fetching all entities from Neo4j...")
        
        all_entities_query = """
        MATCH (n)
        WHERE n.name IS NOT NULL
        RETURN {
            name: n.name,
            type: labels(n)[0],
            module: n.module,
            line_number: n.line_number,
            description: CASE WHEN n.docstring IS NOT NULL THEN n.docstring ELSE '' END
        } as entity
        ORDER BY labels(n)[0], n.name
        LIMIT $limit
        """
        
        result = await neo4j_service.execute_query(all_entities_query, {"limit": top_k})
        
        if not result:
            logger.warning(f"   ⚠️  No entities found in Neo4j")
            return ToolResult(
                success=False,
                error="No entities found in database"
            )
        
        # Extract entities
        entities = []
        for record in result:
            if isinstance(record, dict):
                entity = record.get("entity")
            else:
                entity = record["entity"]
            
            if entity and entity.get("name"):
                entities.append(entity)
        
        logger.info(f"   ✅ Retrieved {len(entities)} entities from Neo4j")
        
        if not entities:
            logger.warning(f"   ⚠️  No valid entities extracted")
            return ToolResult(success=False, error="No valid entities found")
        
        # Log entity types distribution
        type_counts = {}
        for e in entities:
            etype = e.get("type", "Unknown")
            type_counts[etype] = type_counts.get(etype, 0) + 1
        logger.info(f"   📊 Entity types: {type_counts}")
        
        # STEP 2: Use LLM to find best match
        logger.info(f"\n🧠 STEP 2: Using LLM to find best matching entity...")
        
        # Format entities for LLM
        entities_text = "Available entities:\n"
        for i, e in enumerate(entities[:30], 1):  # Show top 30 for clarity
            entities_text += f"{i}. {e.get('name')} (Type: {e.get('type')}, Module: {e.get('module', 'N/A')})\n"
        
        llm_prompt = f"""Given the user query and list of available entities, find the BEST matching entity.

User Query: "{query}"

{entities_text}

Return ONLY a JSON object with:
{{
    "entity_name": "exact name from list",
    "entity_type": "Class/Function/Module/etc",
    "confidence": 0.0-1.0,
    "reason": "why this is the best match"
}}

If no good match exists, return the closest semantic match or related entity."""
        
        openai_api_key = os.getenv("OPENAI_API_KEY")
        if not openai_api_key:
            logger.error("   ❌ OPENAI_API_KEY not set")
            return ToolResult(success=False, error="OpenAI API key not configured")
        
        logger.info(f"   📤 Sending to GPT-4 for entity disambiguation...")
        
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {openai_api_key}"},
                json={
                    "model": "gpt-4",
                    "messages": [
                        {
                            "role": "system",
                            "content": "You are an expert at finding the most relevant code entity for a user query. Always return valid JSON."
                        },
                        {
                            "role": "user",
                            "content": llm_prompt
                        }
                    ],
                    "temperature": 0.3,
                    "max_tokens": 500
                }
            )
        
        if response.status_code != 200:
            logger.error(f"   ❌ OpenAI API error: {response.status_code}")
            return ToolResult(success=False, error=f"LLM request failed: {response.status_code}")
        
        llm_result = response.json()
        llm_response = llm_result["choices"][0]["message"]["content"]
        
        logger.info(f"   🧠 LLM response: {llm_response[:150]}...")
        
        # Parse LLM response
        try:
            # Extract JSON from response (may have extra text)
            json_start = llm_response.find("{")
            json_end = llm_response.rfind("}") + 1
            if json_start >= 0 and json_end > json_start:
                json_str = llm_response[json_start:json_end]
                best_match = json.loads(json_str)
            else:
                logger.error(f"   ❌ Could not find JSON in response")
                return ToolResult(success=False, error="LLM returned invalid response")
        except json.JSONDecodeError as e:
            logger.error(f"   ❌ Failed to parse LLM response: {e}")
            return ToolResult(success=False, error=f"Failed to parse entity selection: {e}")
        
        entity_name = best_match.get("entity_name")
        entity_type = best_match.get("entity_type")
        confidence = best_match.get("confidence", 0)
        reason = best_match.get("reason", "")
        
        logger.info(f"   ✅ Best match: {entity_name} (Type: {entity_type}, Confidence: {confidence})")
        logger.info(f"      Reason: {reason}")
        
        if confidence < 0.5:
            logger.warning(f"   ⚠️  Low confidence match ({confidence})")
        
        # STEP 3: Find entity and get its relationships
        logger.info(f"\n🔗 STEP 3: Fetching entity details and relationships...")
        
        # Find the selected entity in our list
        selected_entity = None
        for e in entities:
            if e.get("name").lower() == entity_name.lower():
                selected_entity = e
                break
        
        if not selected_entity:
            logger.warning(f"   ⚠️  Selected entity not found in list, using LLM suggestion anyway")
            selected_entity = {
                "name": entity_name,
                "type": entity_type,
                "module": "Unknown",
                "line_number": 0
            }
        
        # Get relationships for this entity
        relationships_query = """
        MATCH (e) WHERE toLower(e.name) = toLower($name)
        WITH e
        
        OPTIONAL MATCH (dependent)-[rel_in:IMPORTS|CALLS|INHERITS_FROM|CONTAINS]->(e)
        WITH e, dependent, rel_in, 
             collect({
                 name: dependent.name,
                 type: labels(dependent)[0],
                 relation: type(rel_in),
                 module: dependent.module
             }) as incoming_deps
        
        OPTIONAL MATCH (e)-[rel_out:IMPORTS|CALLS|INHERITS_FROM|CONTAINS]->(dependency)
        WITH e, incoming_deps,
             collect({
                 name: dependency.name,
                 type: labels(dependency)[0],
                 relation: type(rel_out),
                 module: dependency.module
             }) as outgoing_deps
        
        OPTIONAL MATCH (parent)-[rel_contains:CONTAINS]->(e)
        WITH e, incoming_deps, outgoing_deps,
             collect({
                 name: parent.name,
                 type: labels(parent)[0],
                 relation: type(rel_contains)
             }) as parents
        
        RETURN {
            target: e,
            target_type: labels(e)[0],
            target_module: e.module,
            target_line: e.line_number,
            dependents: [d IN incoming_deps WHERE d.name IS NOT NULL],
            dependencies: [d IN outgoing_deps WHERE d.name IS NOT NULL],
            parents: [p IN parents WHERE p.name IS NOT NULL],
            stats: {
                dependents_count: size([d IN incoming_deps WHERE d.name IS NOT NULL]),
                dependencies_count: size([d IN outgoing_deps WHERE d.name IS NOT NULL]),
                parents_count: size([p IN parents WHERE p.name IS NOT NULL])
            }
        } as result
        """
        
        rel_result = await neo4j_service.execute_query(relationships_query, {"name": entity_name})
        
        if rel_result:
            record = rel_result[0]
            result_data = record.get("result") if isinstance(record, dict) else record["result"]
            
            dependents = result_data.get("dependents", [])
            dependencies = result_data.get("dependencies", [])
            parents = result_data.get("parents", [])
            stats = result_data.get("stats", {})
            
            logger.info(f"   ✅ Found relationships: {len(dependents)} dependents, {len(dependencies)} dependencies")
        else:
            dependents = []
            dependencies = []
            parents = []
            stats = {"dependents_count": 0, "dependencies_count": 0, "parents_count": 0}
        
        return ToolResult(
            success=True,
            data={
                "best_match": entity_name,
                "entity_type": entity_type,
                "confidence": confidence,
                "reason": reason,
                "module": selected_entity.get("module", "N/A"),
                "line_number": selected_entity.get("line_number", 0),
                "dependents": dependents,
                "dependencies": dependencies,
                "parents": parents,
                "dependents_count": stats.get("dependents_count", 0),
                "dependencies_count": stats.get("dependencies_count", 0),
                "parents_count": stats.get("parents_count", 0),
                "total_entities_searched": len(entities)
            }
        )
        
    except Exception as e:
        logger.error(f"❌ Exception in find_best_entity_handler: {type(e).__name__}: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return ToolResult(success=False, error=str(e))