"""
Enhanced Graph visualization endpoint using intelligent Cypher generation.

WHAT: Generate Mermaid diagrams with actual relationship connections
WHY: Show how entities relate, depend on, inherit from, or call each other
HOW: 
  1. Extract relationships from Neo4j query results
  2. Build visual graph structure
  3. Use OpenAI to generate beautiful Mermaid diagrams with connections
"""

import json
import os
from typing import Any, List, Dict
from pydantic import BaseModel
from openai import OpenAI
from fastapi import APIRouter, HTTPException

from ...shared.logger import get_logger, generate_correlation_id, set_correlation_id
from ...shared.neo4j_service import get_neo4j_service
from ...shared.relationship_mappings import get_cypher_query_templates, get_query_description  

logger = get_logger(__name__)
router = APIRouter(tags=["visualization"], prefix="/api")

# Request body model for mermaid generation
class GenerateMermaidRequest(BaseModel):
    """Request body for mermaid generation"""
    query_results: List[Dict[str, Any]]


def _extract_all_entities(query_results: List[Dict]) -> Dict[str, List[str]]:
    """
    Extract all unique entities from query results.
    """
    entities = {
        "classes": set(),
        "functions": set(),
        "methods": set(),
        "modules": set(),
        "files": set()
    }
    
    for result in query_results:
        if not isinstance(result, dict):
            continue
        
        # Extract names and types from various result structures
        for key, val in result.items():
            # Only process string values
            if not isinstance(val, str):
                continue
            if not val or val == "None":
                continue
                
            if key in ['c', 'name', 'target', 'source']:
                entities["classes"].add(val)
            elif key == 'module':
                entities["modules"].add(val)
            elif 'function' in key.lower():
                entities["functions"].add(val)
            elif 'method' in key.lower():
                entities["methods"].add(val)
    
    # Convert sets to sorted lists
    return {k: sorted(list(v)) for k, v in entities.items()}


def _build_relationship_connections(query_results: List[Dict]) -> List[Dict[str, Any]]:
    connections = []
    seen = set()
    
    for result in query_results:
        if not isinstance(result, dict):
            continue
        
        # Extract string values only
        source = None
        target = None
        rel_type = "CONNECTS"
        
        for key, val in result.items():
            if isinstance(val, str) and val and val != "None":
                if not source:
                    source = val
                elif not target:
                    target = val
        
        if result.get('relationship_type'):
            rel_type = str(result.get('relationship_type'))
        elif result.get('type'):
            rel_type = str(result.get('type'))
        
        if source and target:
            key = (source, target, rel_type)
            if key not in seen:
                seen.add(key)
                connections.append({
                    "source": source,
                    "target": target,
                    "relationship": rel_type
                })
    
    return connections


@router.post("/graph/generate-mermaid")
async def generate_mermaid(
    entity_name: str, 
    entity_type: str, 
    request: GenerateMermaidRequest
):
    """
    Generate Mermaid diagram code from query results.
    
    This endpoint:
    1. Extracts all entities and relationships from query results
    2. Builds a connection map
    3. Uses OpenAI to generate a beautiful, readable diagram
    4. Handles edge cases (0 relationships, sparse data, etc.)
    
    Args:
        entity_name: Primary entity name
        entity_type: Primary entity type
        request: Request body with query_results
    
    Returns:
        Mermaid diagram code with statistics
    """
    correlation_id = generate_correlation_id()
    set_correlation_id(correlation_id)
    
    try:
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        query_results = request.query_results
        
        # Step 1: Extract entities and relationships
        all_entities = _extract_all_entities(query_results)
        connections = _build_relationship_connections(query_results)
        
        logger.info(
            "Graph data extracted",
            entity=entity_name,
            entities_found=sum(len(v) for v in all_entities.values()),
            connections=len(connections),
            correlation_id=correlation_id
        )
        
        # Step 2: Build prompt for diagram generation
        prompt = f"""Generate a Mermaid mindmap diagram. Return ONLY the code, nothing else.

ENTITY: {entity_name} ({entity_type})

CONNECTIONS: {len(connections)}
{json.dumps(connections[:8], indent=2) if connections else 'NONE'}

OUTPUT FORMAT:
- Start with: mindmap
- Central node: root((EntityName))
- Child nodes: use relationship names as labels
- NO markdown backticks
- NO explanations
- Simple text only

EXAMPLE:
mindmap
  root((Encoding))
    inherits from
      BaseException
    used by
      Request Handler
    methods
      encode
      decode

CREATE THIS DIAGRAM FOR {entity_name}:
"""

        # Step 3: Call OpenAI
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.3,
            max_tokens=2000,
        )
        
        mermaid_code = response.choices[0].message.content.strip()
        
        # FIX: Remove markdown, clean up
        mermaid_code = mermaid_code.replace("```mermaid", "").replace("```", "").strip()
        
        # FIX: Validate it starts with graph
        # Validate and clean
        if not mermaid_code.startswith(("graph", "mindmap")):
            logger.warning("Generated diagram invalid - using fallback")
            mermaid_code = f"""mindmap
                root(({entity_name}))
                    Entity Type
                    {entity_type}"""
        
        logger.info(
            "Mermaid generated successfully",
            entity=entity_name,
            connections=len(connections),
            correlation_id=correlation_id,
        )
        
        return {
            "success": True,
            "mermaid_code": mermaid_code,
            "stats": {
                "total_entities_in_db": sum(len(v) for v in all_entities.values()),
                "direct_connections": len(connections),
                "entity_type": entity_type,
            },
            "correlation_id": correlation_id,
        }
        
    except Exception as e:
        logger.error(f"Mermaid generation failed: {str(e)}", correlation_id=correlation_id)
        raise HTTPException(status_code=500, detail=str(e))