"""
Health check and info endpoints.

WHAT: /health and /agents endpoints
WHY: System health monitoring and service discovery
HOW: Query service status via HTTP
"""

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
import httpx

from ...shared.logger import get_logger, generate_correlation_id, set_correlation_id
from ..dependencies import (
    MEMORY_SERVICE_URL,
    ORCHESTRATOR_SERVICE_URL,
    GRAPH_QUERY_SERVICE_URL,
    CODE_ANALYST_SERVICE_URL,
    INDEXER_SERVICE_URL,
)

logger = get_logger(__name__)
router = APIRouter(tags=["health"])

SERVICES = {
    "memory": MEMORY_SERVICE_URL,
    "orchestrator": ORCHESTRATOR_SERVICE_URL,
    "graph_query": GRAPH_QUERY_SERVICE_URL,
    "code_analyst": CODE_ANALYST_SERVICE_URL,
    "indexer": INDEXER_SERVICE_URL,
}


async def check_service_health(url: str) -> dict:
    """Check if a service is healthy."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{url}/health")
            if response.status_code == 200:
                return response.json()
            return {"status": "unhealthy", "code": response.status_code}
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}


@router.get("/health")
async def health_check():
    """
    Health check endpoint.

    Returns:
        Health status of all MCP services
    """
    correlation_id = generate_correlation_id()
    set_correlation_id(correlation_id)

    try:
        services = {}
        for name, url in SERVICES.items():
            services[name] = await check_service_health(url)

        overall_status = "healthy" if all(
            s.get("status") == "healthy" for s in services.values()
        ) else "degraded"

        health = {
            "status": overall_status,
            "services": services,
            "correlation_id": correlation_id,
        }

        logger.info("Health check completed", status=overall_status)
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
    List all available MCP services.

    Returns:
        List of services
    """
    correlation_id = generate_correlation_id()
    set_correlation_id(correlation_id)

    return {
        "services": list(SERVICES.keys()),
        "correlation_id": correlation_id,
    }
