"""Orchestrator Service - FastAPI application setup."""

import os
from typing import Any, Dict, Optional
from fastapi import FastAPI, HTTPException

from .service import OrchestratorService
from ...shared.logger import get_logger

logger = get_logger(__name__)

# ============================================================================
# FASTAPI APP SETUP
# ============================================================================

app = FastAPI(title="Orchestrator Service", version="1.0.0")
orchestrator_service: OrchestratorService = None


@app.on_event("startup")
async def startup():
    """Initialize orchestrator service on startup."""
    global orchestrator_service
    orchestrator_service = OrchestratorService()
    await orchestrator_service.initialize()


@app.on_event("shutdown")
async def shutdown():
    """Cleanup on shutdown."""
    if orchestrator_service:
        await orchestrator_service.shutdown()


# ============================================================================
# HEALTH & INFO ENDPOINTS
# ============================================================================

@app.get("/health")
async def health():
    """Health check endpoint."""
    if not orchestrator_service:
        raise HTTPException(status_code=503, detail="Service not initialized")
    
    pg_healthy = await orchestrator_service.postgres_client.health_check()
    redis_healthy = await orchestrator_service.redis_client.health_check()
    
    if not (pg_healthy and redis_healthy):
        raise HTTPException(status_code=503, detail="Backend connection failed")
    
    return {
        "status": "healthy",
        "service": "OrchestratorService",
        "postgres": "ok" if pg_healthy else "error",
        "redis": "ok" if redis_healthy else "error",
        "tools": len(orchestrator_service.tools)
    }


@app.get("/tools")
async def get_tools():
    """Get available tools schema."""
    if not orchestrator_service:
        raise HTTPException(status_code=503, detail="Service not initialized")
    
    return {
        "service": "OrchestratorService",
        "tools": orchestrator_service.get_tools_schema()
    }


# ============================================================================
# TOOL EXECUTION ENDPOINT
# ============================================================================

@app.post("/execute")
async def execute_tool(tool_input: Dict[str, Any]):
    """
    Main entry point for tool execution.
    
    Gateway sends: {"query": "...", "session_id": "...optional"}
    Always routes to execute_query handler (full orchestration pipeline)
    
    Request:
    {
        "query": "What is FastAPI?",
        "session_id": "550e8400-e29b-41d4-a716-446655440000"
    }
    
    Response:
    {
        "success": true,
        "data": {
            "response": "FastAPI is...",
            "agents_used": ["graph_query", "code_analyst"],
            "intent": "explain",
            "entities_found": ["FastAPI"],
            "session_id": "550e8400-e29b-41d4-a716-446655440000",
            "num_agents": 2
        },
        "error": null
    }
    """
    if not orchestrator_service:
        raise HTTPException(status_code=503, detail="Service not initialized")
    
    try:
        # Extract query and session_id from input
        query = tool_input.get("query")
        session_id = tool_input.get("session_id")
        
        if not query:
            raise HTTPException(status_code=400, detail="query is required")
        
        logger.info(f"🎯 /execute received: {query[:80]}... session_id={session_id}")
        
        # ALWAYS use execute_query as the main entry point
        # This handles: analyze → route → call agents → synthesize → store
        result = await orchestrator_service.execute_tool(
            "execute_query",
            {"query": query, "session_id": session_id}
        )
        
        logger.info(f"✅ /execute completed: success={result.success}")
        
        # Return in standard format
        return {
            "success": result.success,
            "data": result.data,
            "error": result.error
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ /execute error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))



# ============================================================================
# ENTRY POINT
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app,
        host=os.getenv("ORCHESTRATOR_HOST", "0.0.0.0"),
        port=int(os.getenv("ORCHESTRATOR_PORT", 8001))
    )
