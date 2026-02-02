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
    """
    Extract connections from the actual Neo4j query result structure.
    Results have keys: c, cd, f, d, parent, calls_target, method, fd, md
    Where each represents a different optional relationship path.
    """
    connections = []
    seen = set()
    
    for result in query_results:
        if not isinstance(result, dict):
            continue
        
        source = result.get('c')  # Always the central Class node
        if not source or not isinstance(source, dict):
            continue
        
        source_name = source.get('name')
        if not source_name:
            continue
        
        # Check each possible relationship type
        # HAS_METHOD -> method
        if result.get('method') and isinstance(result['method'], dict):
            target = result['method']
            target_name = target.get('name')
            if target_name:
                conn_key = (source_name, target_name, 'HAS_METHOD')
                if conn_key not in seen:
                    seen.add(conn_key)
                    connections.append({
                        "source": source_name,
                        "target": target_name,
                        "relationship": "HAS_METHOD"
                    })
        
        # INHERITS_FROM -> parent
        if result.get('parent') and isinstance(result['parent'], dict):
            target = result['parent']
            target_name = target.get('name')
            if target_name:
                conn_key = (source_name, target_name, 'INHERITS_FROM')
                if conn_key not in seen:
                    seen.add(conn_key)
                    connections.append({
                        "source": source_name,
                        "target": target_name,
                        "relationship": "INHERITS_FROM"
                    })
        
        # CALLS -> calls_target
        if result.get('calls_target') and isinstance(result['calls_target'], dict):
            target = result['calls_target']
            target_name = target.get('name')
            if target_name:
                conn_key = (source_name, target_name, 'CALLS')
                if conn_key not in seen:
                    seen.add(conn_key)
                    connections.append({
                        "source": source_name,
                        "target": target_name,
                        "relationship": "CALLS"
                    })
        
        # DOCUMENTED_BY -> cd
        if result.get('cd') and isinstance(result['cd'], dict):
            target = result['cd']
            target_name = target.get('name')
            if target_name:
                conn_key = (source_name, target_name, 'DOCUMENTED_BY')
                if conn_key not in seen:
                    seen.add(conn_key)
                    connections.append({
                        "source": source_name,
                        "target": target_name,
                        "relationship": "DOCUMENTED_BY"
                    })
        
        # Additional relationships from other optional matches
        # CONTAINS -> f, d (file/docstring)
        for key in ['f', 'd']:
            if result.get(key) and isinstance(result[key], dict):
                target = result[key]
                target_name = target.get('name')
                if target_name:
                    rel_type = "CONTAINS"
                    conn_key = (source_name, target_name, rel_type)
                    if conn_key not in seen:
                        seen.add(conn_key)
                        connections.append({
                            "source": source_name,
                            "target": target_name,
                            "relationship": rel_type
                        })
    
    logger.info(
        "Connection extraction complete",
        total_connections=len(connections),
        sample_connections=str(connections[:3])
    )
    
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
        
        # 🔍 LOG THE ACTUAL MERMAID CODE
        logger.info(
            "Raw mermaid code from OpenAI",
            mermaid_code=mermaid_code[:500],  # First 500 chars
            entity=entity_name,
            correlation_id=correlation_id,
        )
        
        # FIX: Validate it starts with graph
        # Validate and clean
        if not mermaid_code.startswith(("graph", "mindmap")):
            logger.warning("Generated diagram invalid - using fallback")
            logger.warning(
                "Invalid mermaid code detected",
                first_chars=mermaid_code[:50],
                correlation_id=correlation_id,
            )
            mermaid_code = f"""mindmap
  root(({entity_name}))
    Entity Type
    {entity_type}"""
        
        # 🔍 LOG FINAL MERMAID CODE
        logger.info(
            "Mermaid generated successfully",
            final_mermaid_code=mermaid_code,
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