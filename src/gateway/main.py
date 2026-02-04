"""
FastAPI Gateway - Minimal service discovery and health checks.

Streamlit calls Orchestrator directly. Gateway only provides:
- Service discovery
- Health monitoring
- CORS handling
"""
from fastapi import FastAPI, HTTPException

import os
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import httpx
from .models import ChatRequest, ChatResponse

from .routes import health
from ..shared.logger import get_logger

logger = get_logger(__name__)

# Global clients
orchestrator_url: str = os.getenv("ORCHESTRATOR_SERVICE_URL", "http://localhost:8001")
http_client: Optional[httpx.AsyncClient] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage app lifecycle - startup and shutdown."""
    global http_client
    
    # Startup
    logger.info("Gateway starting up...")
    http_client = httpx.AsyncClient(timeout=30.0)
    
    yield
    
    # Shutdown
    logger.info("Gateway shutting down...")
    if http_client:
        await http_client.aclose()


# Create FastAPI app
app = FastAPI(
    title="Agentic Codebase Chat - Gateway",
    description="Service discovery and health monitoring for multi-agent system",
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

# Add request logging middleware
@app.middleware("http")
async def log_requests(request, call_next):
    """Log all requests for debugging."""
    method = request.method
    path = request.url.path
    
    logger.info(f"→ {method} {path}")
    
    try:
        response = await call_next(request)
        logger.info(f"← {method} {path} {response.status_code}")
        return response
    except Exception as e:
        logger.error(f"✗ {method} {path} error: {e}")
        raise

# Include health router
app.include_router(health.router, tags=["health"])

# ============================================================================
# SERVICE DISCOVERY
# ============================================================================

@app.get("/")
async def root():
    """Root endpoint with service URLs."""
    return {
        "name": "Agentic Codebase Chat - Gateway",
        "version": "2.0.0",
        "description": "Multi-agent system gateway for FastAPI repository analysis",
        "message": "Streamlit calls Orchestrator directly at /orchestrator_service URL",
        "services": {
            "orchestrator": orchestrator_url,
            "memory": os.getenv("MEMORY_SERVICE_URL", "http://localhost:8005"),
            "graph_query": os.getenv("GRAPH_QUERY_SERVICE_URL", "http://localhost:8003"),
            "code_analyst": os.getenv("CODE_ANALYST_SERVICE_URL", "http://localhost:8004"),
            "indexer": os.getenv("INDEXER_SERVICE_URL", "http://localhost:8002")
        },
        "status": "ready"
    }


@app.get("/health")
async def gateway_health():
    """Gateway and Orchestrator health check."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            orch_resp = await client.get(f"{orchestrator_url}/health")
        
        orchestrator_healthy = orch_resp.status_code == 200
        
        return {
            "status": "healthy" if orchestrator_healthy else "degraded",
            "gateway": "ok",
            "orchestrator": "ok" if orchestrator_healthy else "error",
            "services": {
                "orchestrator": orchestrator_url
            }
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return {
            "status": "unhealthy",
            "gateway": "ok",
            "orchestrator": "error",
            "error": str(e)
        }


@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    """
    Main chat endpoint - receives query, routes to Orchestrator.
    
    Flow: Gateway → Orchestrator → Agents → Synthesis → Response
    
    Args:
        request: ChatRequest with query and optional session_id
        
    Returns:
        ChatResponse with synthesized answer and agents used
    """
    try:
        logger.info(f"→ POST /api/chat: {request.query[:100]}")
        
        # Forward to Orchestrator's /execute endpoint
        response = await http_client.post(
            f"{orchestrator_url}/execute",
            json={
                "query": request.query,
                "session_id": request.session_id
            },
            timeout=60.0
        )
        
        if response.status_code != 200:
            logger.error(f"Orchestrator error: {response.text}")
            raise HTTPException(status_code=response.status_code, detail=response.text)
        
        result = response.json()
        logger.info(f"← POST /api/chat: success - {len(result.get('response', ''))} chars")
        
        # Map orchestrator response to ChatResponse model
        return ChatResponse(
            success=result.get("success", False),
            response=result.get("response", "No response generated"),
            agents_used=result.get("agents_used", []),
            intent=result.get("intent"),
            entities_found=result.get("entities_found", []),
            session_id=result.get("session_id"),
            error=result.get("error")
        )
        
    except httpx.TimeoutException:
        logger.error("Orchestrator timeout")
        raise HTTPException(status_code=504, detail="Orchestrator request timed out")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Chat error: {e}")
        raise HTTPException(status_code=500, detail=str(e))



@app.get("/api")
async def api_info():
    """Service URLs and configuration."""
    return {
        "version": "2.0.0",
        "architecture": "Gateway → Orchestrator flow",
        "endpoints": {
            "POST /api/chat": "Send query",
            "GET /health": "Health check",
            "GET /api": "This info"
        }
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app,
        host=os.getenv("GATEWAY_HOST", "0.0.0.0"),
        port=int(os.getenv("GATEWAY_PORT", 8000))
    )