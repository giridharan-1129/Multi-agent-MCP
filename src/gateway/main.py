"""
FastAPI Gateway - Main entry point for the multi-agent system.

Routes requests to the Orchestrator Service (MCP).
Manages sessions, caching, and response aggregation.
"""

import os
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException, WebSocket, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import httpx

from .routes import (
    agentic_chat,
    rag_chat,
    chat,
    health,
    indexing,
    embeddings,
    query,
    graph_visualization,
    analysis,
    websocket,
)
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

# ============================================================================
# HEALTH CHECK
# ============================================================================

@app.get("/health")
async def health_check():
    """Check gateway and all services health."""
    health_status = {
        "gateway": "healthy",
        "timestamp": None,
        "services": {}
    }
    
    try:
        # Check orchestrator
        async with httpx.AsyncClient(timeout=5.0) as client:
            try:
                resp = await client.get(f"{orchestrator_url}/health")
                health_status["services"]["orchestrator"] = "healthy" if resp.status_code == 200 else "unhealthy"
            except Exception as e:
                health_status["services"]["orchestrator"] = "unreachable"
                logger.warning(f"Orchestrator health check failed: {e}")
        
        # Check Redis
        if redis_client:
            redis_ok = await redis_client.health_check()
            health_status["services"]["redis"] = "healthy" if redis_ok else "unhealthy"
    
    except Exception as e:
        health_status["gateway"] = "unhealthy"
        logger.error(f"Health check failed: {e}")
    
    return health_status


# ============================================================================
# SERVICE ROUTES
# ============================================================================

# Include routers
app.include_router(health.router, prefix="/api", tags=["health"])
app.include_router(agentic_chat.router, prefix="/api", tags=["chat"])
app.include_router(rag_chat.router, prefix="/api", tags=["chat"])
app.include_router(chat.router, prefix="/api", tags=["chat"])
app.include_router(indexing.router, prefix="/api", tags=["indexing"])
app.include_router(embeddings.router, prefix="/api", tags=["embeddings"])
app.include_router(query.router, prefix="/api", tags=["query"])
app.include_router(graph_visualization.router, prefix="/api", tags=["graph"])
app.include_router(analysis.router, prefix="/api", tags=["analysis"])
app.include_router(websocket.router, tags=["websocket"])

# ============================================================================
# ORCHESTRATOR PROXY ROUTE
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
            "chat": "/api/agentic-chat",
            "rag": "/api/rag-chat",
            "indexing": "/api/index",
            "graph": "/api/graph/statistics",
            "websocket": "/ws/chat"
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
