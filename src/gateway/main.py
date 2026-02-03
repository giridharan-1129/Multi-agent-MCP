"""
FastAPI Gateway - Main entry point for the multi-agent system.

Routes requests to the Orchestrator Service (MCP).
Manages sessions, caching, and response aggregation.
"""

import os
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import httpx

from .routes import health
from ..shared.logger import get_logger
from ..shared.redis_client import RedisClientManager

logger = get_logger(__name__)

# Global clients
orchestrator_url: str = os.getenv("ORCHESTRATOR_SERVICE_URL", "http://localhost:8001")
http_client: Optional[httpx.AsyncClient] = None
redis_client: Optional[RedisClientManager] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage app lifecycle - startup and shutdown."""
    global http_client, redis_client
    
    # Startup
    logger.info("Gateway starting up...")
    http_client = httpx.AsyncClient(timeout=30.0)
    
    try:
        redis_url = os.getenv("REDIS_URL", "redis://:redis_password@localhost:6379/2")
        redis_client = RedisClientManager(redis_url)
        logger.info("Redis client initialized")
    except Exception as e:
        logger.warning(f"Redis connection failed: {e}")
    
    yield
    
    # Shutdown
    logger.info("Gateway shutting down...")
    if http_client:
        await http_client.aclose()
    if redis_client:
        redis_client.close()


# Create FastAPI app
app = FastAPI(
    title="Agentic Codebase Chat - Gateway",
    description="Multi-agent system gateway for FastAPI repository analysis",
    version="2.0.0",
    lifespan=lifespan
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(health.router, tags=["health"])

# ============================================================================
# ORCHESTRATOR PROXY ROUTES
# ============================================================================

@app.get("/api/orchestrator/tools")
async def get_orchestrator_tools():
    """Get available orchestrator tools."""
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{orchestrator_url}/tools")
            if resp.status_code == 200:
                return resp.json()
            else:
                raise HTTPException(status_code=resp.status_code, detail="Orchestrator unavailable")
    except Exception as e:
        logger.error(f"Failed to get orchestrator tools: {e}")
        raise HTTPException(status_code=503, detail="Orchestrator service unavailable")


@app.post("/api/orchestrator/execute")
async def execute_orchestrator_tool(tool_name: str, tool_input: dict):
    """Execute a tool on the orchestrator service."""
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{orchestrator_url}/execute?tool_name={tool_name}",
                json=tool_input
            )
            if resp.status_code == 200:
                return resp.json()
            else:
                raise HTTPException(status_code=resp.status_code, detail="Tool execution failed")
    except Exception as e:
        logger.error(f"Failed to execute orchestrator tool: {e}")
        raise HTTPException(status_code=503, detail="Orchestrator service unavailable")


# ============================================================================
# ROOT ROUTES
# ============================================================================

@app.get("/")
async def root():
    """Root endpoint with API info."""
    return {
        "name": "Agentic Codebase Chat",
        "version": "2.0.0",
        "description": "Multi-agent system for FastAPI repository analysis",
        "endpoints": {
            "health": "/health",
            "orchestrator_tools": "/api/orchestrator/tools",
            "orchestrator_execute": "/api/orchestrator/execute",
        },
        "orchestrator": orchestrator_url
    }


@app.get("/api")
async def api_info():
    """API information."""
    return {
        "version": "2.0.0",
        "services": {
            "orchestrator": orchestrator_url,
            "memory": os.getenv("MEMORY_SERVICE_URL", "http://localhost:8005"),
            "graph_query": os.getenv("GRAPH_QUERY_SERVICE_URL", "http://localhost:8003"),
            "code_analyst": os.getenv("CODE_ANALYST_SERVICE_URL", "http://localhost:8004"),
            "indexer": os.getenv("INDEXER_SERVICE_URL", "http://localhost:8002")
        }
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app,
        host=os.getenv("GATEWAY_HOST", "0.0.0.0"),
        port=int(os.getenv("GATEWAY_PORT", 8000))
    )
