"""Code Analyst Service - FastAPI entry point."""

import os
from typing import Any, Dict

from fastapi import FastAPI, HTTPException

from .service import CodeAnalystService
from ...shared.logger import get_logger

logger = get_logger(__name__)

# Global service instance
analyst_service: CodeAnalystService = None


# ============================================================================
# FastAPI App Setup
# ============================================================================

app = FastAPI(
    title="Code Analyst Service",
    description="MCP Server for code analysis and pattern detection",
    version="1.0.0"
)


# ============================================================================
# Lifecycle Events
# ============================================================================

@app.on_event("startup")
async def startup():
    """Initialize code analyst service on startup."""
    global analyst_service
    analyst_service = CodeAnalystService()
    await analyst_service.initialize()
    logger.info("Code Analyst Service started")


@app.on_event("shutdown")
async def shutdown():
    """Cleanup on shutdown."""
    global analyst_service
    if analyst_service:
        await analyst_service.shutdown()
    logger.info("Code Analyst Service stopped")


# ============================================================================
# MCP Standard Endpoints
# ============================================================================

@app.get("/health")
async def health():
    """Health check endpoint."""
    if not analyst_service:
        raise HTTPException(status_code=503, detail="Service not initialized")
    
    db_healthy = await analyst_service.neo4j_service.verify_connection()
    
    if not db_healthy:
        raise HTTPException(status_code=503, detail="Neo4j connection failed")
    
    return {
        "status": "healthy",
        "service": "CodeAnalystService",
        "neo4j": "ok",
        "tools": len(analyst_service.tools)
    }


@app.get("/tools")
async def get_tools():
    """Get available MCP tools schema."""
    if not analyst_service:
        raise HTTPException(status_code=503, detail="Service not initialized")
    
    return {
        "service": "CodeAnalystService",
        "tools": analyst_service.get_tools_schema()
    }


@app.post("/execute")
async def execute_tool(tool_name: str, tool_input: Dict[str, Any]):
    """Execute an MCP tool by name."""
    if not analyst_service:
        raise HTTPException(status_code=503, detail="Service not initialized")
    
    result = await analyst_service.execute_tool(tool_name, tool_input)
    return result.dict()


# ============================================================================
# Entry Point
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app,
        host=os.getenv("CODE_ANALYST_HOST", "0.0.0.0"),
        port=int(os.getenv("CODE_ANALYST_PORT", 8004))
    )
