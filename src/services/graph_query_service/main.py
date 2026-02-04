"""Graph Query Service - FastAPI entry point."""

import os
from typing import Any, Dict

from fastapi import FastAPI, HTTPException

from .service import GraphQueryService
from ...shared.logger import get_logger

logger = get_logger(__name__)

# ============================================================================
# FastAPI App Setup
# ============================================================================

app = FastAPI(
    title="Graph Query Service",
    description="MCP Server for Neo4j knowledge graph operations",
    version="1.0.0"
)

# Global service instance
graph_service: GraphQueryService = None


@app.on_event("startup")
async def startup():
    """Initialize graph query service on startup."""
    global graph_service
    graph_service = GraphQueryService()
    await graph_service.initialize()
    logger.info("Graph Query Service started")


@app.on_event("shutdown")
async def shutdown():
    """Cleanup on shutdown."""
    global graph_service
    if graph_service:
        await graph_service.shutdown()
    logger.info("Graph Query Service stopped")


# ============================================================================
# FastAPI App Setup
# ============================================================================

app = FastAPI(
    title="Graph Query Service",
    description="MCP Server for Neo4j knowledge graph operations",
    version="1.0.0"
)


# ============================================================================
# MCP Standard Endpoints
# ============================================================================

@app.get("/health")
async def health():
    """Health check endpoint."""
    if not graph_service:
        raise HTTPException(status_code=503, detail="Service not initialized")
    
    db_healthy = await graph_service.neo4j_service.verify_connection()
    
    if not db_healthy:
        raise HTTPException(status_code=503, detail="Neo4j connection failed")
    
    return {
        "status": "healthy",
        "service": "GraphQueryService",
        "neo4j": "ok",
        "tools": len(graph_service.tools)
    }


@app.get("/tools")
async def get_tools():
    """Get available MCP tools schema."""
    if not graph_service:
        raise HTTPException(status_code=503, detail="Service not initialized")
    
    return {
        "service": "GraphQueryService",
        "tools": graph_service.get_tools_schema()
    }


@app.post("/execute")
async def execute_tool(tool_name: str, tool_input: Dict[str, Any]):
    """Execute an MCP tool by name."""
    if not graph_service:
        raise HTTPException(status_code=503, detail="Service not initialized")
    
    result = await graph_service.execute_tool(tool_name, tool_input)
    return result.dict()


# ============================================================================
# Entry Point
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app,
        host=os.getenv("GRAPH_QUERY_HOST", "0.0.0.0"),
        port=int(os.getenv("GRAPH_QUERY_PORT", 8003))
    )
