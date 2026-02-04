"""
Health check and info endpoints.

WHAT: /health and /agents endpoints
WHY: System health monitoring and service discovery
HOW: Query service status via HTTP
"""

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
import httpx
import asyncio

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
    """Check if a service is healthy with retry logic."""
    max_retries = 3
    retry_delay = 2  # seconds
    
    for attempt in range(max_retries):
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(f"{url}/health")
                if response.status_code == 200:
                    return response.json()
                elif attempt < max_retries - 1:
                    # Retry on non-200
                    import asyncio
                    await asyncio.sleep(retry_delay)
                    continue
                else:
                    return {"status": "unhealthy", "code": response.status_code}
        except Exception as e:
            if attempt < max_retries - 1:
                # Retry on connection error
                import asyncio
                await asyncio.sleep(retry_delay)
                continue
            else:
                return {"status": "unhealthy", "error": str(e)}
    
    return {"status": "unhealthy", "error": "Max retries exceeded"}


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

        # Count healthy vs unhealthy
        healthy_count = sum(1 for s in services.values() if s.get("status") == "healthy")
        total_count = len(services)
        
        # Status logic
        if healthy_count == total_count:
            overall_status = "healthy"
        elif healthy_count >= total_count * 0.7:  # 70% threshold
            overall_status = "degraded"
        else:
            overall_status = "unhealthy"

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
