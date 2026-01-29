"""
FastAPI Gateway - Main API Server.

WHAT: FastAPI application that serves as entry point for the system
WHY: Provides REST API endpoints for users to interact with agents
HOW: Routes requests to agents, manages sessions, returns responses

Example:
    # Run with: uvicorn src.gateway.main:app --reload
    # Access at: http://localhost:8000
"""

from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from ..shared.config import config
from ..shared.logger import get_logger, generate_correlation_id, set_correlation_id
from ..shared.neo4j_service import init_neo4j_service, get_neo4j_service
from ..agents.orchestrator_agent import OrchestratorAgent
from ..agents.indexer_agent import IndexerAgent
from ..agents.graph_query_agent import GraphQueryAgent
from ..agents.code_analyst_agent import CodeAnalystAgent

logger = get_logger(__name__)

# Global agent instances
orchestrator: Optional[OrchestratorAgent] = None
indexer: Optional[IndexerAgent] = None
graph_query: Optional[GraphQueryAgent] = None
code_analyst: Optional[CodeAnalystAgent] = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager for startup and shutdown.

    Args:
        app: FastAPI application
    """
    # Startup
    logger.info("Gateway starting up")
    
    try:
        # Initialize Neo4j
        await init_neo4j_service(
            uri=config.neo4j.uri,
            username=config.neo4j.username,
            password=config.neo4j.password,
            database=config.neo4j.database,
        )
        logger.info("Neo4j service initialized")

        # Initialize agents
        global orchestrator, indexer, graph_query, code_analyst
        
        orchestrator = OrchestratorAgent()
        await orchestrator.startup()
        
        indexer = IndexerAgent()
        await indexer.startup()
        
        graph_query = GraphQueryAgent()
        await graph_query.startup()
        
        code_analyst = CodeAnalystAgent()
        await code_analyst.startup()
        
        logger.info("All agents started")

    except Exception as e:
        logger.error("Failed to start gateway", error=str(e))
        raise

    yield

    # Shutdown
    logger.info("Gateway shutting down")
    
    try:
        if orchestrator:
            await orchestrator.shutdown()
        if indexer:
            await indexer.shutdown()
        if graph_query:
            await graph_query.shutdown()
        if code_analyst:
            await code_analyst.shutdown()
        
        neo4j = get_neo4j_service()
        await neo4j.close()
        
        logger.info("Gateway shut down successfully")
    except Exception as e:
        logger.error("Error during shutdown", error=str(e))


# Create FastAPI app
app = FastAPI(
    title="FastAPI Multi-Agent Chat System",
    description="Multi-agent system for analyzing FastAPI repository",
    version="1.0.0",
    lifespan=lifespan,
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ========================
# Request/Response Models
# ========================


class ChatRequest(BaseModel):
    """Chat request model."""

    query: str
    """User query"""

    session_id: Optional[str] = None
    """Optional session ID"""


class ChatResponse(BaseModel):
    """Chat response model."""

    session_id: str
    """Session ID"""

    response: str
    """Response text"""

    agents_used: list
    """Agents that were used"""

    correlation_id: str
    """Correlation ID for tracing"""


class IndexRequest(BaseModel):
    """Repository indexing request."""

    repo_url: str
    """Repository URL"""

    full_index: bool = True
    """Whether to do full index"""


class IndexResponse(BaseModel):
    """Repository indexing response."""

    status: str
    """Indexing status"""

    files_processed: int
    """Number of files processed"""

    entities_created: int
    """Number of entities created"""

    relationships_created: int
    """Number of relationships created"""


# ========================
# Health and Info Endpoints
# ========================


@app.get("/health")
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
                    "name": orchestrator.name if orchestrator else "unknown",
                    "status": "healthy" if orchestrator and orchestrator.is_healthy else "offline",
                },
                "indexer": {
                    "name": indexer.name if indexer else "unknown",
                    "status": "healthy" if indexer and indexer.is_healthy else "offline",
                },
                "graph_query": {
                    "name": graph_query.name if graph_query else "unknown",
                    "status": "healthy" if graph_query and graph_query.is_healthy else "offline",
                },
                "code_analyst": {
                    "name": code_analyst.name if code_analyst else "unknown",
                    "status": "healthy" if code_analyst and code_analyst.is_healthy else "offline",
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


@app.get("/agents")
async def list_agents():
    """
    List all available agents.

    Returns:
        List of agents with their tools
    """
    correlation_id = generate_correlation_id()
    set_correlation_id(correlation_id)

    agents_info = []

    if orchestrator:
        agents_info.append({
            "name": orchestrator.name,
            "description": orchestrator.description,
            "tools": orchestrator.list_tools(),
        })

    if indexer:
        agents_info.append({
            "name": indexer.name,
            "description": indexer.description,
            "tools": indexer.list_tools(),
        })

    if graph_query:
        agents_info.append({
            "name": graph_query.name,
            "description": graph_query.description,
            "tools": graph_query.list_tools(),
        })

    if code_analyst:
        agents_info.append({
            "name": code_analyst.name,
            "description": code_analyst.description,
            "tools": code_analyst.list_tools(),
        })

    logger.info("Agents listed", count=len(agents_info))
    return {
        "agents": agents_info,
        "correlation_id": correlation_id,
    }


# ========================
# Chat Endpoints
# ========================


@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    Chat with the system.

    Args:
        request: Chat request with query and optional session_id

    Returns:
        Chat response with answer and session info
    """
    correlation_id = generate_correlation_id()
    set_correlation_id(correlation_id)

    try:
        if not orchestrator:
            raise HTTPException(status_code=503, detail="Orchestrator not initialized")

        logger.info(
            "Chat request received",
            query=request.query[:100],
            session_id=request.session_id,
        )

        # Create or get session
        session_id = request.session_id
        if not session_id:
            # Create new session
            create_result = await orchestrator.execute_tool(
                "create_conversation",
                {},
            )
            if create_result.success:
                session_id = create_result.data.get("session_id")
            else:
                raise HTTPException(status_code=500, detail="Failed to create session")

        # Analyze query
        analysis_result = await orchestrator.execute_tool(
            "analyze_query",
            {
                "query": request.query,
                "session_id": session_id,
            },
        )

        if not analysis_result.success:
            raise HTTPException(status_code=400, detail="Query analysis failed")

        analysis = analysis_result.data
        agents_used = analysis.get("required_agents", ["orchestrator"])

        # Add user message to conversation
        await orchestrator.execute_tool(
            "add_conversation_message",
            {
                "session_id": session_id,
                "role": "user",
                "content": request.query,
            },
        )

        # For now, create a simple response
        # In a full implementation, would call other agents based on analysis
        response_text = f"I analyzed your query about {', '.join(analysis.get('entities', ['code']))}. "
        response_text += f"This appears to be a {analysis.get('intent', 'general')} question. "
        response_text += f"I would route this to: {', '.join(agents_used)}."

        # Add assistant message to conversation
        await orchestrator.execute_tool(
            "add_conversation_message",
            {
                "session_id": session_id,
                "role": "assistant",
                "content": response_text,
                "agent_name": "orchestrator",
            },
        )

        logger.info(
            "Chat response generated",
            session_id=session_id,
            agents=len(agents_used),
        )

        return ChatResponse(
            session_id=session_id,
            response=response_text,
            agents_used=agents_used,
            correlation_id=correlation_id,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Chat request failed", error=str(e), correlation_id=correlation_id)
        raise HTTPException(status_code=500, detail=str(e))


# ========================
# Indexing Endpoints
# ========================


@app.post("/api/index", response_model=IndexResponse)
async def index_repository(request: IndexRequest):
    """
    Index a GitHub repository.

    Args:
        request: Indexing request with repo URL

    Returns:
        Indexing result with statistics
    """
    correlation_id = generate_correlation_id()
    set_correlation_id(correlation_id)

    try:
        if not indexer:
            raise HTTPException(status_code=503, detail="Indexer agent not initialized")

        logger.info(
            "Index request received",
            repo_url=request.repo_url,
        )

        # Execute indexing
        result = await indexer.execute_tool(
            "index_repository",
            {
                "repo_url": request.repo_url,
                "full_index": request.full_index,
            },
        )

        if not result.success:
            raise HTTPException(status_code=400, detail=result.error)

        data = result.data

        logger.info(
            "Repository indexed",
            repo_url=request.repo_url,
            entities=data.get("entities_created"),
        )

        return IndexResponse(
            status=data.get("status", "success"),
            files_processed=data.get("files_processed", 0),
            entities_created=data.get("entities_created", 0),
            relationships_created=data.get("relationships_created", 0),
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Index request failed", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/index/status")
async def get_index_status():
    """
    Get knowledge graph statistics.

    Returns:
        Graph statistics
    """
    correlation_id = generate_correlation_id()
    set_correlation_id(correlation_id)

    try:
        if not indexer:
            raise HTTPException(status_code=503, detail="Indexer agent not initialized")

        result = await indexer.execute_tool("get_index_status", {})

        if not result.success:
            raise HTTPException(status_code=400, detail=result.error)

        logger.info("Index status retrieved")
        return {
            "status": "ok",
            "statistics": result.data,
            "correlation_id": correlation_id,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get index status", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


# ========================
# Query Endpoints
# ========================


@app.post("/api/query/find")
async def find_entity(name: str, entity_type: Optional[str] = None):
    """
    Find an entity in the knowledge graph.

    Args:
        name: Entity name
        entity_type: Optional type filter

    Returns:
        Entity data if found
    """
    correlation_id = generate_correlation_id()
    set_correlation_id(correlation_id)

    try:
        if not graph_query:
            raise HTTPException(status_code=503, detail="Graph query agent not initialized")

        result = await graph_query.execute_tool(
            "find_entity",
            {
                "name": name,
                "entity_type": entity_type,
            },
        )

        if not result.success:
            raise HTTPException(status_code=404, detail=result.error)

        logger.info("Entity found", name=name)
        return {
            "entity": result.data.get("entity"),
            "correlation_id": correlation_id,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to find entity", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/query/execute")
async def execute_query(payload: dict):
    neo4j = get_neo4j_service()
    query = payload.get("query")
    params = payload.get("params", {})

    if not query:
        return {"error": "query is required"}

    result = await neo4j.execute_query(query, params)
    return {"result": result}

@app.post("/api/query/dependencies")
async def get_dependencies(name: str):
    """
    Get dependencies of an entity.

    Args:
        name: Entity name

    Returns:
        List of dependencies
    """
    correlation_id = generate_correlation_id()
    set_correlation_id(correlation_id)

    try:
        if not graph_query:
            raise HTTPException(status_code=503, detail="Graph query agent not initialized")

        result = await graph_query.execute_tool(
            "get_dependencies",
            {"name": name},
        )

        if not result.success:
            raise HTTPException(status_code=400, detail=result.error)

        logger.info("Dependencies retrieved", entity=name)
        return {
            "entity": name,
            "dependencies": result.data.get("dependencies", []),
            "count": result.data.get("count", 0),
            "correlation_id": correlation_id,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get dependencies", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


# ========================
# Analysis Endpoints
# ========================


@app.post("/api/analysis/function")
async def analyze_function(name: str, module: Optional[str] = None):
    """
    Analyze a function.

    Args:
        name: Function name
        module: Optional module filter

    Returns:
        Function analysis
    """
    correlation_id = generate_correlation_id()
    set_correlation_id(correlation_id)

    try:
        if not code_analyst:
            raise HTTPException(status_code=503, detail="Code analyst agent not initialized")

        result = await code_analyst.execute_tool(
            "analyze_function",
            {
                "name": name,
                "module": module,
            },
        )

        if not result.success:
            raise HTTPException(status_code=404, detail=result.error)

        logger.info("Function analyzed", name=name)
        return {
            "analysis": result.data,
            "correlation_id": correlation_id,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to analyze function", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,
        host=config.gateway_host,
        port=config.gateway_port,
        reload=config.gateway_reload,
    )
