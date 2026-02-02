"""
Knowledge graph query endpoints.

WHAT: /api/query/* endpoints
WHY: Search and traverse the knowledge graph
HOW: Use Graph Query Agent to find entities and relationships
"""

from typing import Optional
from fastapi import APIRouter, HTTPException
from openai import OpenAI
import os
from ...shared.logger import get_logger, generate_correlation_id, set_correlation_id
from ...shared.neo4j_service import get_neo4j_service
from ..dependencies import get_graph_query

logger = get_logger(__name__)
router = APIRouter(tags=["query"], prefix="/api/query")

@router.post("/find")
async def find_entity(payload: dict):
    """
    Find an entity in the knowledge graph.

    Args:
        payload: {"name": "EntityName", "entity_type": "Class"} (optional)

    Returns:
        Entity data if found
    """
    correlation_id = generate_correlation_id()
    set_correlation_id(correlation_id)

    try:
        name = payload.get("name")
        entity_type = payload.get("entity_type")
        
        if not name:
            raise HTTPException(status_code=400, detail="name is required")
        
        graph_query = get_graph_query()

        result = await graph_query.execute_tool(
            "find_entity",
            {
                "name": name,
                "entity_type": entity_type,
            },
        )

        if not result.success:
            raise HTTPException(status_code=404, detail=result.error)

        logger.info("Entity found", name=name)
        return {
            "entity": result.data.get("entity"),
            "correlation_id": correlation_id,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to find entity", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/execute")
async def execute_query(payload: dict):
    """
    Execute a custom Cypher query against Neo4j.

    Args:
        payload: {"query": "...", "params": {...}}

    Returns:
        Query results
    """
    correlation_id = generate_correlation_id()
    set_correlation_id(correlation_id)

    try:
        neo4j = get_neo4j_service()
        query = payload.get("query")
        params = payload.get("params", {})

        if not query:
            raise HTTPException(status_code=400, detail="query is required")

        logger.info("Query executed", query=query[:100])
        result = await neo4j.execute_query(query, params)
        return {
            "result": result,
            "correlation_id": correlation_id,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to execute query", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/dependencies")
async def get_dependencies(payload: dict):
    """
    Get dependencies of an entity.

    Args:
        payload: {"name": "EntityName"}

    Returns:
        List of dependencies
    """
    correlation_id = generate_correlation_id()
    set_correlation_id(correlation_id)

    try:
        name = payload.get("name")
        
        if not name:
            raise HTTPException(status_code=400, detail="name is required")
        
        graph_query = get_graph_query()

        result = await graph_query.execute_tool(
            "get_dependencies",
            {"name": name},
        )

        if not result.success:
            raise HTTPException(status_code=400, detail=result.error)

        logger.info("Dependencies retrieved", entity=name)
        return {
            "entity": name,
            "dependencies": result.data.get("dependencies", []),
            "count": result.data.get("count", 0),
            "correlation_id": correlation_id,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get dependencies", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/dependents")
async def get_dependents(payload: dict):
    """
    Get entities that depend on this entity.

    Args:
        payload: {"name": "EntityName"}

    Returns:
        List of dependents
    """
    correlation_id = generate_correlation_id()
    set_correlation_id(correlation_id)

    try:
        name = payload.get("name")
        
        if not name:
            raise HTTPException(status_code=400, detail="name is required")
        
        graph_query = get_graph_query()

        result = await graph_query.execute_tool(
            "get_dependents",
            {"name": name},
        )

        if not result.success:
            raise HTTPException(status_code=400, detail=result.error)

        logger.info("Dependents retrieved", entity=name)
        return {
            "entity": name,
            "dependents": result.data.get("dependents", []),
            "count": result.data.get("count", 0),
            "correlation_id": correlation_id,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get dependents", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/related")
async def get_related(payload: dict):
    """
    Get entities related by a specific relationship type.

    Args:
        payload: {"name": "EntityName", "relationship": "CALLS"} (optional)

    Returns:
        Related entities
    """
    correlation_id = generate_correlation_id()
    set_correlation_id(correlation_id)

    try:
        name = payload.get("name")
        relationship = payload.get("relationship")
        
        if not name:
            raise HTTPException(status_code=400, detail="name is required")
        
        graph_query = get_graph_query()

        result = await graph_query.execute_tool(
                "get_relationships",
                {
                    "name": name,
                    "relationship": relationship,
                },
            )

        if not result.success:
            raise HTTPException(status_code=400, detail=result.error)

        logger.info("Related entities retrieved", entity=name, relationship=relationship)
        return {
            "entity": name,
            "relationships": result.data.get("relationships", []),
            "count": result.data.get("count", 0),
            "correlation_id": correlation_id,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get related entities", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/inheritance")
async def get_inheritance(payload: dict):
    """
    Find all classes that inherit from a given class.

    Args:
        payload: {"name": "APIRouter"}

    Returns:
        List of classes that inherit from the specified class
    """
    correlation_id = generate_correlation_id()
    set_correlation_id(correlation_id)

    try:
        name = payload.get("name")
        
        if not name:
            raise HTTPException(status_code=400, detail="name is required")
        
        neo4j = get_neo4j_service()

        # Query: Find classes that inherit from the target class
        cypher = """
        MATCH (parent:Class {name: $name})
        OPTIONAL MATCH (child:Class)-[:INHERITS_FROM]->(parent)
        RETURN {
            parent_class: parent.name,
            parent_module: parent.module,
            child_classes: collect(DISTINCT {
                name: child.name,
                module: child.module,
                line_number: child.line_number
            })
        } as inheritance
        """
        
        results = await neo4j.execute_query(cypher, {"name": name})
        
        if not results:
            logger.warning(f"No inheritance found for {name}")
            return {
                "parent_class": name,
                "child_classes": [],
                "message": f"No classes found that inherit from {name}",
                "correlation_id": correlation_id,
            }
        
        inheritance = results[0].get("inheritance", {})
        child_classes = inheritance.get("child_classes", [])
        
        logger.info(f"Found {len(child_classes)} classes inheriting from {name}")
        
        return {
            "parent_class": name,
            "child_classes": child_classes,
            "count": len(child_classes),
            "correlation_id": correlation_id,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get inheritance", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))
        
@router.post("/extract-keywords")
async def extract_keywords(payload: dict):
    """
    Extract keywords and entities from a query using LLM.
    Used by agents to understand what context to retrieve.
    
    Input: {"query": "How does dependency injection work?"}
    Output: {
        "query": "...",
        "keywords": ["dependency", "injection"],
        "entities": ["Depends", "FastAPI"],
        "intent": "explanation"
    }
    """
    correlation_id = generate_correlation_id()
    set_correlation_id(correlation_id)
    
    try:
        query = payload.get("query")
        
        if not query:
            raise HTTPException(status_code=400, detail="query is required")
        
        logger.info("Extracting keywords", query=query[:100])
        
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
        
        prompt = f"""Extract keywords and entities from this code question.

Query: {query}

Return ONLY JSON (no markdown, no explanation):
{{
    "keywords": ["word1", "word2"],
    "entities": ["Class", "Function"],
    "intent": "explanation|search|analysis|comparison"
}}

Examples:
- "How does FastAPI handle dependency injection?" → 
  {{"keywords": ["dependency", "injection", "handle"], "entities": ["FastAPI", "Depends"], "intent": "explanation"}}
  
- "Show me APIRouter" →
  {{"keywords": ["apiRouter"], "entities": ["APIRouter"], "intent": "search"}}
"""
        
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0,
        )
        
        import json
        result_text = response.choices[0].message.content.strip()
        result = json.loads(result_text)
        
        logger.info(
            "Keywords extracted",
            keywords=result.get("keywords"),
            entities=result.get("entities"),
            intent=result.get("intent"),
        )
        
        return {
            "query": query,
            "keywords": result.get("keywords", []),
            "entities": result.get("entities", []),
            "intent": result.get("intent", "general"),
            "correlation_id": correlation_id,
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to extract keywords", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))