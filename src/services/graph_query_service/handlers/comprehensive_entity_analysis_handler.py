"""Handler for finding ALL relevant entities using LLM and fetching their relationships."""

import json
from typing import Any, Dict, List
from ....shared.mcp_server import ToolResult
from ....shared.neo4j_service import Neo4jService
from ....shared.logger import get_logger
import httpx
import os

logger = get_logger(__name__)


async def comprehensive_entity_analysis_handler(
    neo4j_service: Neo4jService,
    query: str,
    top_k: int = 5
) -> ToolResult:
    """
    Comprehensive entity analysis - fetches ALL nodes, ranks by relevance, returns relationships.
    
    1. Fetch ALL entities from Neo4j (grouped by type)
    2. Use LLM to find TOP-K most relevant entities
    3. For each entity, fetch exhaustive relationships
    4. Return aggregated entity + relationship data
    """
    try:
        logger.info(f"🔍 find_all_best_entities_handler called")
        logger.info(f"   📝 Query: {query[:80]}...")
        logger.info(f"   🎯 Finding top {top_k} entities")
        
        # ============================================================================
        # STEP 1: Fetch ALL entities grouped by type
        # ============================================================================
        logger.info(f"\n📊 STEP 1: Fetching all entities from Neo4j (grouped by type)...")
        
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
        LIMIT 200
        """
        
        result = await neo4j_service.execute_query(all_entities_query, {"limit": 200})
        
        if not result:
            logger.warning(f"   ⚠️  No entities found in Neo4j")
            return ToolResult(success=False, error="No entities found in database")
        
        # Extract and group entities
        entities = []
        entity_types_dict = {}
        
        for record in result:
            entity = record.get("entity") if isinstance(record, dict) else record["entity"]
            if entity and entity.get("name"):
                entities.append(entity)
                etype = entity.get("type", "Unknown")
                if etype not in entity_types_dict:
                    entity_types_dict[etype] = []
                entity_types_dict[etype].append(entity.get("name"))
        
        logger.info(f"   ✅ Retrieved {len(entities)} total entities from Neo4j")
        logger.info(f"   📊 Entity types breakdown:")
        for etype, names in entity_types_dict.items():
            logger.info(f"      - {etype}: {len(names)} entities")
        
        if not entities:
            logger.warning(f"   ⚠️  No valid entities extracted")
            return ToolResult(success=False, error="No valid entities found")
        
        # ============================================================================
        # STEP 2: Use LLM to find TOP-K most relevant entities
        # ============================================================================
        logger.info(f"\n STEP 2: Using LLM to find top {top_k} relevant entities...")
        
        # Format entities for LLM - INCLUDE ALL entities for better matching
        logger.info(f"   📝 Building entity list for LLM ({len(entities)} total entities)...")
        entities_text = "Available entities in codebase:\n\n"
        
        for etype, names in entity_types_dict.items():
            entities_text += f"{etype}s ({len(names)}):\n"
            # ✅ CHANGED: Include ALL names, not just first 10
            for name in sorted(names):  # Sort for consistency
                entities_text += f"  - {name}\n"
            entities_text += "\n"
        
        logger.debug(f"   📏 Entity list size: {len(entities_text)} chars")
        logger.debug(f"   📄 First 500 chars:\n{entities_text[:500]}...")
        
        llm_prompt = f"""You are an expert at finding relevant code entities in a Python codebase. 

User Query: "{query}"

Below is the COMPLETE list of all entities in the codebase. Your job is to find the TOP {top_k} entities that match this query.

{entities_text}

INSTRUCTIONS:
1. Search for entities that DIRECTLY match the query keywords
2. Look for exact name matches, substring matches, or semantically related entities
3. Return the TOP {top_k} most relevant entities (or fewer if not found)
4. Rank by relevance to the query (highest confidence first)
5. For each entity, explain WHY it matches the query

CRITICAL RULES:
- Return ONLY a valid JSON array. No markdown, no preamble, no explanation.
- If you find fewer than {top_k} entities, return just those.
- If you find NO entities, return an empty array: []

JSON Format (MUST be valid JSON):
[
  {{"entity_name": "Dependant", "entity_type": "Class", "confidence": 0.95, "reason": "Exactly matches query keyword"}},
  {{"entity_name": "Dependency", "entity_type": "Class", "confidence": 0.75, "reason": "Related to query about dependencies"}}
]

Requirements:
- entity_name: MUST exist in the list above
- entity_type: Class, Function, Module, etc.
- confidence: Float between 0.0 and 1.0
- reason: Brief explanation of relevance"""
        
        logger.info(f"   📊 LLM prompt prepared ({len(llm_prompt)} chars)")
        
        openai_api_key = os.getenv("OPENAI_API_KEY")
        if not openai_api_key:
            logger.error("   ❌ OPENAI_API_KEY not set")
            return ToolResult(success=False, error="OpenAI API key not configured")
        
        logger.info(f"   📤 Sending to GPT-4 for entity ranking...")
        
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    "https://api.openai.com/v1/chat/completions",
                    headers={"Authorization": f"Bearer {openai_api_key}"},
                    json={
                        "model": "gpt-4",
                        "messages": [
                            {
                                "role": "system",
                                "content": "You are an expert at finding the most relevant code entities for a user query. Return ONLY valid JSON array, no extra text."
                            },
                            {
                                "role": "user",
                                "content": llm_prompt
                            }
                        ],
                        "temperature": 0.3,
                        "max_tokens": 800
                    }
                )
        except httpx.TimeoutException:
            logger.error(f"   ❌ OpenAI API timeout (60s)")
            return ToolResult(success=False, error="LLM request timed out - query too complex")
        
        if response.status_code != 200:
            logger.error(f"   ❌ OpenAI API error: {response.status_code}")
            return ToolResult(success=False, error=f"LLM request failed: {response.status_code}")
        
        llm_result = response.json()
        llm_response = llm_result["choices"][0]["message"]["content"]
        
        logger.info(f"    LLM response received: {llm_response[:100]}...")
        
        # Parse LLM response
        # Parse LLM response - robust JSON extraction
        top_entities = []
        try:
            json_start = llm_response.find("[")
            json_end = llm_response.rfind("]") + 1
            
            if json_start >= 0 and json_end > json_start:
                json_str = llm_response[json_start:json_end]
                top_entities = json.loads(json_str)
                logger.info(f"   ✅ Parsed {len(top_entities)} entities from LLM response")
            else:
                logger.warning(f"   ⚠️  No JSON array found in response, returning empty list")
                # Return success with empty list instead of failing
                return ToolResult(
                    success=True,
                    data={
                        "query": query,
                        "total_entities_in_codebase": len(entities),
                        "relevant_entities": [],
                        "relevant_count": 0,
                        "total_relationships": 0,
                        "message": "LLM could not identify relevant entities for this query"
                    }
                )
        except json.JSONDecodeError as e:
            logger.warning(f"   ⚠️  Failed to parse JSON: {e}, returning empty list")
            # Return success with empty list instead of failing
            return ToolResult(
                success=True,
                data={
                    "query": query,
                    "total_entities_in_codebase": len(entities),
                    "relevant_entities": [],
                    "relevant_count": 0,
                    "total_relationships": 0,
                    "message": "Could not parse LLM response"
                }
            )
        
        logger.info(f"   ✅ LLM selected {len(top_entities)} relevant entities")
        for entity in top_entities:
            logger.info(f"      - {entity.get('entity_name')} ({entity.get('entity_type')}, confidence: {entity.get('confidence')})")
        
        # ============================================================================
        # STEP 3: For each entity, fetch exhaustive relationships
        # ============================================================================
        logger.info(f"\n🔗 STEP 3: Fetching relationships for each entity...")
        
        entities_with_relationships = []
        
        for entity_info in top_entities:
            entity_name = entity_info.get("entity_name")
            entity_type = entity_info.get("entity_type")
            confidence = entity_info.get("confidence")
            reason = entity_info.get("reason")
            
            logger.info(f"   📍 Fetching relationships for: {entity_name} ({entity_type})")
            logger.debug(f"      → Searching for entity with name: {entity_name}")
            
            # FIRST: Verify entity exists in Neo4j
            verify_entity_query = """
            MATCH (e) WHERE toLower(e.name) = toLower($name)
            RETURN {
                name: e.name,
                type: labels(e)[0],
                module: e.module,
                line: e.line_number,
                found: true
            } as entity_info
            LIMIT 1
            """
            
            logger.debug(f"      ⏳ Verifying entity exists...")
            verify_result = await neo4j_service.execute_query(verify_entity_query, {"name": entity_name})
            
            if not verify_result:
                logger.warning(f"      ❌ Entity NOT FOUND in Neo4j: '{entity_name}'")
                logger.debug(f"         This entity was returned by LLM but doesn't exist in database")
                # Still continue but with 0 relationships
                entity_with_rel = {
                    "entity_name": entity_name,
                    "entity_type": entity_type,
                    "confidence": confidence,
                    "reason": reason,
                    "module": "N/A",
                    "line_number": 0,
                    "dependents": [],
                    "dependencies": [],
                    "parents": [],
                    "dependents_count": 0,
                    "dependencies_count": 0,
                    "parents_count": 0,
                    "error": f"Entity not found in Neo4j database"
                }
                entities_with_relationships.append(entity_with_rel)
                continue
            else:
                entity_found = verify_result[0]
                entity_data = entity_found.get("entity_info") if isinstance(entity_found, dict) else entity_found["entity_info"]
                logger.debug(f"      ✅ Entity found: {entity_data.get('name')} ({entity_data.get('type')})")
            
            # Get relationships for this entity
            relationships_query = """
            MATCH (e) WHERE toLower(e.name) = toLower($name)
            WITH e
            
            OPTIONAL MATCH (dependent)-[rel_in:IMPORTS|CALLS|INHERITS_FROM|CONTAINS]->(e)
            WITH e, dependent, rel_in, 
                 collect(DISTINCT {
                     name: dependent.name,
                     type: labels(dependent)[0],
                     relation: type(rel_in),
                     module: dependent.module
                 }) as incoming_deps
            
            OPTIONAL MATCH (e)-[rel_out:IMPORTS|CALLS|INHERITS_FROM|CONTAINS]->(dependency)
            WITH e, incoming_deps,
                 collect(DISTINCT {
                     name: dependency.name,
                     type: labels(dependency)[0],
                     relation: type(rel_out),
                     module: dependency.module
                 }) as outgoing_deps
            
            OPTIONAL MATCH (parent)-[rel_contains:CONTAINS]->(e)
            WITH e, incoming_deps, outgoing_deps,
                 collect(DISTINCT {
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
            
            logger.debug(f"      ⏳ Executing relationship query...")
            
            try:
                rel_result = await neo4j_service.execute_query(relationships_query, {"name": entity_name})
                logger.debug(f"      Query result: {rel_result is not None}")
                
                if rel_result:
                    logger.debug(f"      Got {len(rel_result)} result(s)")
                    record = rel_result[0]
                    logger.debug(f"      Record type: {type(record).__name__}")
                    logger.debug(f"      Record keys: {list(record.keys()) if isinstance(record, dict) else 'not a dict'}")
                    
                    result_data = record.get("result") if isinstance(record, dict) else record["result"]
                    logger.debug(f"      Result data type: {type(result_data).__name__}")
                    
                    dependents = result_data.get("dependents", [])
                    dependencies = result_data.get("dependencies", [])
                    parents = result_data.get("parents", [])
                    stats = result_data.get("stats", {})
                    
                    logger.debug(f"      Dependents: {len(dependents)} items")
                    logger.debug(f"      Dependencies: {len(dependencies)} items")
                    logger.debug(f"      Parents: {len(parents)} items")
                else:
                    logger.warning(f"      ⚠️  Query returned no results")
                    dependents = []
                    dependencies = []
                    parents = []
                    stats = {"dependents_count": 0, "dependencies_count": 0, "parents_count": 0}
                
                logger.info(f"      ✅ Found: {stats.get('dependents_count', 0)} dependents, {stats.get('dependencies_count', 0)} dependencies, {stats.get('parents_count', 0)} parents")
                
                entity_with_rel = {
                    "entity_name": entity_name,
                    "entity_type": entity_type,
                    "confidence": confidence,
                    "reason": reason,
                    "module": result_data.get("target_module", "N/A") if rel_result else "N/A",
                    "line_number": result_data.get("target_line", 0) if rel_result else 0,
                    "dependents": dependents,
                    "dependencies": dependencies,
                    "parents": parents,
                    "dependents_count": stats.get("dependents_count", 0),
                    "dependencies_count": stats.get("dependencies_count", 0),
                    "parents_count": stats.get("parents_count", 0)
                }
                
                entities_with_relationships.append(entity_with_rel)
                
            except Exception as e:
                logger.warning(f"      ⚠️  Failed to fetch relationships for {entity_name}: {e}")
                # Still include entity even if relationships fail
                entity_with_rel = {
                    "entity_name": entity_name,
                    "entity_type": entity_type,
                    "confidence": confidence,
                    "reason": reason,
                    "module": "N/A",
                    "line_number": 0,
                    "dependents": [],
                    "dependencies": [],
                    "parents": [],
                    "dependents_count": 0,
                    "dependencies_count": 0,
                    "parents_count": 0,
                    "error": str(e)
                }
                entities_with_relationships.append(entity_with_rel)
        
        logger.info(f"\n✅ COMPLETE: Analyzed {len(entities_with_relationships)} entities with relationships")
        
        return ToolResult(
            success=True,
            data={
                "query": query,
                "total_entities_in_codebase": len(entities),
                "relevant_entities": entities_with_relationships,
                "relevant_count": len(entities_with_relationships),
                "total_relationships": sum(
                    e.get("dependents_count", 0) + 
                    e.get("dependencies_count", 0) + 
                    e.get("parents_count", 0)
                    for e in entities_with_relationships
                )
            }
        )
        
    except Exception as e:
        logger.error(f"❌ Exception in find_all_best_entities_handler: {type(e).__name__}: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return ToolResult(success=False, error=str(e))