"""
Health check and info endpoints.

WHAT: /health and /agents endpoints
WHY: System health monitoring and agent discovery
HOW: Query agent status and Neo4j statistics
"""

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

from ...shared.logger import get_logger, generate_correlation_id, set_correlation_id
from ...shared.neo4j_service import get_neo4j_service
from ..dependencies import (
    get_orchestrator,
    get_indexer,
    get_graph_query,
    get_code_analyst,
)

logger = get_logger(__name__)
router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check():
    """
    Health check endpoint.

    Returns:
        Health status of all components
    """
    correlation_id = generate_correlation_id()
    set_correlation_id(correlation_id)

    try:
        neo4j = get_neo4j_service()
        stats = await neo4j.get_graph_statistics()

        health = {
            "status": "healthy",
            "components": {
                "orchestrator": {
                    "name": get_orchestrator().name,
                    "status": "healthy" if get_orchestrator().is_healthy else "offline",
                },
                "indexer": {
                    "name": get_indexer().name,
                    "status": "healthy" if get_indexer().is_healthy else "offline",
                },
                "graph_query": {
                    "name": get_graph_query().name,
                    "status": "healthy" if get_graph_query().is_healthy else "offline",
                },
                "code_analyst": {
                    "name": get_code_analyst().name,
                    "status": "healthy" if get_code_analyst().is_healthy else "offline",
                },
                "neo4j": {
                    "status": "healthy",
                    "statistics": stats,
                },
            },
            "correlation_id": correlation_id,
        }

        logger.info("Health check passed")
        return health

    except Exception as e:
        logger.error("Health check failed", error=str(e))
        return JSONResponse(
            status_code=503,
            content={
                "status": "unhealthy",
                "error": str(e),
                "correlation_id": correlation_id,
            },
        )


@router.get("/agents")
async def list_agents():
    """
    List all available agents.

    Returns:
        List of agents with their tools
    """
    correlation_id = generate_correlation_id()
    set_correlation_id(correlation_id)

    agents_info = []

    try:
        agents_info.append({
            "name": get_orchestrator().name,
            "description": get_orchestrator().description,
            "tools": get_orchestrator().list_tools(),
        })

        agents_info.append({
            "name": get_indexer().name,
            "description": get_indexer().description,
            "tools": get_indexer().list_tools(),
        })

        agents_info.append({
            "name": get_graph_query().name,
            "description": get_graph_query().description,
            "tools": get_graph_query().list_tools(),
        })

        agents_info.append({
            "name": get_code_analyst().name,
            "description": get_code_analyst().description,
            "tools": get_code_analyst().list_tools(),
        })

        logger.info("Agents listed", count=len(agents_info))
        return {
            "agents": agents_info,
            "correlation_id": correlation_id,
        }

    except Exception as e:
        logger.error("Failed to list agents", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))
