"""Memory Service - FastAPI entry point."""

import os
from typing import Any, Dict

from fastapi import FastAPI, HTTPException

from .service import MemoryService
from ...shared.logger import get_logger

logger = get_logger(__name__)

# Global service instance
memory_service: MemoryService = None


# ============================================================================
# FastAPI App Setup
# ============================================================================

app = FastAPI(
    title="Memory Service",
    description="MCP Server for conversation memory management",
    version="1.0.0"
)


# ============================================================================
# Lifecycle Events
# ============================================================================

@app.on_event("startup")
async def startup():
    """Initialize memory service on startup."""
    global memory_service
    memory_service = MemoryService()
    await memory_service.initialize()
    logger.info("Memory Service started")


@app.on_event("shutdown")
async def shutdown():
    """Cleanup on shutdown."""
    global memory_service
    if memory_service:
        await memory_service.shutdown()
    logger.info("Memory Service stopped")


# ============================================================================
# MCP Standard Endpoints
# ============================================================================

@app.get("/health")
async def health():
    """Health check endpoint."""
    if not memory_service:
        raise HTTPException(status_code=503, detail="Service not initialized")
    
    pg_healthy = await memory_service.postgres_client.health_check()
    redis_healthy = await memory_service.redis_client.health_check()
    
    if not (pg_healthy and redis_healthy):
        raise HTTPException(status_code=503, detail="Database connection failed")
    
    return {
        "status": "healthy",
        "service": "MemoryService",
        "postgres": "ok" if pg_healthy else "error",
        "redis": "ok" if redis_healthy else "error",
        "tools": len(memory_service.tools)
    }


@app.get("/tools")
async def get_tools():
    """Get available MCP tools schema."""
    if not memory_service:
        raise HTTPException(status_code=503, detail="Service not initialized")
    
    return {
        "service": "MemoryService",
        "tools": memory_service.get_tools_schema()
    }


@app.post("/execute")
async def execute_tool(tool_name: str, tool_input: Dict[str, Any]):
    """Execute an MCP tool by name."""
    if not memory_service:
        raise HTTPException(status_code=503, detail="Service not initialized")
    
    result = await memory_service.execute_tool(tool_name, tool_input)
    return {
        "success": result.success,
        "data": result.data,
        "error": result.error
    }


# ============================================================================
# Entry Point
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app,
        host=os.getenv("MEMORY_HOST", "0.0.0.0"),
        port=int(os.getenv("MEMORY_PORT", 8005))
    )
