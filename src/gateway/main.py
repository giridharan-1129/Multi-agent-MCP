"""
FastAPI Gateway - Main API Server.

WHAT: FastAPI application entry point
WHY: Creates app, manages lifespan, registers routes
HOW: Initialize agents, setup middleware, include route routers
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from ..shared.config import config
from ..shared.logger import get_logger, generate_correlation_id, set_correlation_id
from ..shared.neo4j_service import init_neo4j_service, get_neo4j_service
from ..shared.pinecone_embeddings_service import init_embeddings_service
from ..agents.orchestrator_agent import OrchestratorAgent
from ..agents.indexer_agent import IndexerAgent
from ..agents.graph_query_agent import GraphQueryAgent
from ..agents.code_analyst_agent import CodeAnalystAgent
from .dependencies import init_agents, shutdown_agents
from .routes import (
    rag_chat_router,
    health_router,
    chat_router,
    websocket_router,
    indexing_router,
    query_router,
    analysis_router,
    embeddings_router,
    graph_visualization_router,
)

logger = get_logger(__name__)


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

        # Initialize Embeddings Service (Pinecone)
        try:
            await init_embeddings_service()
            logger.info("✅ Pinecone embeddings service initialized")
        except Exception as e:
            logger.warning(f"⚠️ Pinecone embeddings service initialization failed: {str(e)}")
            logger.info("Continuing with Neo4j-only search (semantic search disabled)")

        # 1️⃣ Create agents FIRST
        logger.info("🤖 Creating MCP agents...")
        
        orchestrator = OrchestratorAgent()
        logger.info("✅ Orchestrator Agent created")
        
        indexer = IndexerAgent()
        logger.info("✅ Indexer Agent created")
        
        graph_query = GraphQueryAgent()
        logger.info("✅ Graph Query Agent created")
        
        code_analyst = CodeAnalystAgent()
        logger.info("✅ Code Analyst Agent created")

        # 2️⃣ Start agents
        await orchestrator.startup()
        await indexer.startup()
        await graph_query.startup()
        await code_analyst.startup()

        # 3️⃣ Wire dependencies (DI)
        orchestrator.graph_query_agent = graph_query
        orchestrator.code_analyst_agent = code_analyst
        orchestrator.indexer_agent = indexer

        # 4️⃣ Store globally
        init_agents(orchestrator, indexer, graph_query, code_analyst)

        # 5️⃣ WebSocket wiring
        from .websocket_manager import ws_manager
        ws_manager.set_orchestrator(orchestrator)


        logger.info("All agents started")

    except Exception:
        logger.exception("Failed to start gateway")
        raise

    yield

    # Shutdown
    logger.info("Gateway shutting down")
    
    try:
        # Get current instances
        from .dependencies import (
            get_orchestrator,
            get_indexer,
            get_graph_query,
            get_code_analyst,
        )
        
        try:
            await get_orchestrator().shutdown()
        except:
            pass
            
        try:
            await get_indexer().shutdown()
        except:
            pass
            
        try:
            await get_graph_query().shutdown()
        except:
            pass
            
        try:
            await get_code_analyst().shutdown()
        except:
            pass
        
        neo4j = get_neo4j_service()
        await neo4j.close()
        
        shutdown_agents()
        
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

# Include route routers
app.include_router(health_router)
app.include_router(chat_router)
app.include_router(websocket_router)
app.include_router(indexing_router)
app.include_router(query_router)
app.include_router(analysis_router)
app.include_router(rag_chat_router)
app.include_router(graph_visualization_router)
app.include_router(embeddings_router)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        app,
        host=config.gateway_host,
        port=config.gateway_port,
        reload=config.gateway_reload,
    )
