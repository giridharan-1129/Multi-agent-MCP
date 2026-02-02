"""
Graph visualization endpoint using intelligent Cypher generation.

WHAT: Generate Mermaid diagrams using schema-aware Cypher queries
WHY: Combine predefined query templates (reliable) with LLM for synthesis (flexible)
HOW: 
  1. Use relationship_mappings to generate queries based on node type
  2. Execute all queries on Neo4j in parallel-like fashion
  3. Collect and aggregate results
  4. Use OpenAI to generate beautiful Mermaid code from results
  5. Return Mermaid code to render
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


@router.post("/graph/generate-cypher")
async def generate_cypher(entity_name: str, entity_type: str):
    """
    Generate MULTIPLE optimized Cypher queries based on node type.
    
    Uses schema-aware templates instead of LLM to ensure reliability.
    Returns a list of queries that explore different relationship patterns.
    
    Args:
        entity_name: Name of entity (e.g., "FastAPI")
        entity_type: Type of entity (e.g., "Class", "Function", "Package")
    
    Returns:
        List of Cypher queries with description
    """
    correlation_id = generate_correlation_id()
    set_correlation_id(correlation_id)
    
    try:
        # Get queries based on node type - deterministic and reliable
        cypher_queries = get_cypher_query_templates(entity_type, entity_name)
        query_description = get_query_description(entity_type)
        
        logger.info(
            "Cypher queries generated from templates",
            entity=entity_name,
            type=entity_type,
            query_count=len(cypher_queries),
            correlation_id=correlation_id,
        )
        
        return {
            "success": True,
            "queries": cypher_queries,
            "description": query_description,
            "query_count": len(cypher_queries),
            "correlation_id": correlation_id,
        }
        
    except Exception as e:
        logger.error(f"Cypher generation failed: {str(e)}", correlation_id=correlation_id)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/graph/execute-cypher")
async def execute_cypher(cypher: str = None, entity_name: str = None):
    """
    Execute Cypher query(ies) with automatic error recovery.
    
    Supports both:
    - Single query: ?cypher=<query> (deprecated)
    - Multiple queries: POST with list (recommended)
    
    Args:
        cypher: Single Cypher query string (optional)
        entity_name: Entity name for parameter substitution
    
    Returns:
        Query results
    """
    correlation_id = generate_correlation_id()
    set_correlation_id(correlation_id)
    
    try:
        neo4j = get_neo4j_service()
        
        if not cypher:
            raise HTTPException(status_code=400, detail="cypher parameter required")
        
        # Execute query
        results = await neo4j.execute_query(cypher, {"name": entity_name} if entity_name else {})
        
        logger.info(
            "Cypher executed successfully",
            entity=entity_name,
            results_count=len(results),
            correlation_id=correlation_id
        )
        
        return {
            "success": True,
            "results": results,
            "count": len(results),
            "correlation_id": correlation_id,
        }
        
    except Exception as e:
        logger.error(f"Cypher execution failed: {str(e)}", correlation_id=correlation_id)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/graph/generate-mermaid")
async def generate_mermaid(
    entity_name: str, 
    entity_type: str, 
    request: GenerateMermaidRequest
):
    """
    Generate Mermaid diagram code from query results.
    
    Takes results from multiple queries (or a single query) and uses OpenAI
    to generate a beautiful, readable Mermaid diagram.
    
    Args:
        entity_name: Entity name (query param)
        entity_type: Entity type (query param)
        request: Request body with query_results from /api/query/execute
    
    Returns:
        Mermaid diagram code with statistics
    """
    correlation_id = generate_correlation_id()
    set_correlation_id(correlation_id)
    
    try:
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        
        # Extract results from request body
        query_results = request.query_results
        
        # Flatten results in case they're nested
        flattened_results = []
        for result in query_results:
            if isinstance(result, dict):
                # Could be nested like {"results": {...}}
                if "results" in result:
                    flattened_results.append(result["results"])
                else:
                    flattened_results.append(result)
            else:
                flattened_results.append(result)
        
        # Extract relationships
        outgoing = []
        incoming = []
        
        for item in flattened_results:
            if isinstance(item, dict):
                outgoing.extend(item.get("outgoing", []))
                incoming.extend(item.get("incoming", []))
        
        # Filter out None/null values
        outgoing = [r for r in outgoing if r and r.get("target")]
        incoming = [r for r in incoming if r and r.get("source")]
        
        # Remove duplicates while preserving order
        seen_out = set()
        unique_outgoing = []
        for r in outgoing:
            key = (r.get("target"), r.get("relationship"))
            if key not in seen_out:
                seen_out.add(key)
                unique_outgoing.append(r)
        outgoing = unique_outgoing[:10]  # Limit for readability
        
        seen_in = set()
        unique_incoming = []
        for r in incoming:
            key = (r.get("source"), r.get("relationship"))
            if key not in seen_in:
                seen_in.add(key)
                unique_incoming.append(r)
        incoming = unique_incoming[:10]  # Limit for readability
        
        prompt = f"""Generate a beautiful Mermaid diagram for code entity relationships.

Entity: {entity_name} (Type: {entity_type})

OUTGOING RELATIONSHIPS (what this entity uses/depends on):
{json.dumps(outgoing, indent=2)}

INCOMING RELATIONSHIPS (what depends on this entity):
{json.dumps(incoming, indent=2)}

MERMAID REQUIREMENTS:
1. Use graph LR (left to right layout)
2. Central node: large, distinctive (use bright color like #FF6B6B)
3. Outgoing dependencies: blue (#4ECDC4)
4. Incoming dependents: orange (#FFE66D)
5. Edge labels: show relationship type (CALLS, INHERITS_FROM, etc.)
6. Limit nodes for readability (max 8-10 each direction)
7. Use short, clear node IDs (c1, f1, p1, etc.)
8. Proper Mermaid syntax: graph LR, A["label"], A -->|rel| B
9. Add styling with classDef
10. ONLY output valid Mermaid code - NO markdown, NO explanation

Start with: graph LR
End with: classDef statements for styling"""

        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            max_tokens=1500,
        )
        
        mermaid_code = response.choices[0].message.content.strip()
        
        # Clean markdown if present
        if mermaid_code.startswith("```"):
            mermaid_code = mermaid_code.split("```")[1]
            if mermaid_code.startswith("mermaid"):
                mermaid_code = mermaid_code[7:]
            mermaid_code = mermaid_code.strip()
        
        logger.info(
            "Mermaid generated successfully",
            entity=entity_name,
            entity_type=entity_type,
            outgoing_count=len(outgoing),
            incoming_count=len(incoming),
            correlation_id=correlation_id,
        )
        
        return {
            "success": True,
            "mermaid_code": mermaid_code,
            "stats": {
                "outgoing_count": len(outgoing),
                "incoming_count": len(incoming),
                "total_relationships": len(outgoing) + len(incoming),
            },
            "correlation_id": correlation_id,
        }
        
    except Exception as e:
        logger.error(f"Mermaid generation failed: {str(e)}", correlation_id=correlation_id)
        raise HTTPException(status_code=500, detail=str(e))