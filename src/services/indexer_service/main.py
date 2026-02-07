"""
Indexer Service - MCP Server for repository indexing.

Minimal core implementation:
- Service initialization
- Tool registration
- Request routing to handlers
"""

import os
from typing import Any, Dict
from fastapi import FastAPI, HTTPException

from ...shared.mcp_server import BaseMCPServer, ToolResult
from ...shared.neo4j_service import Neo4jService
from ...shared.ast_parser import ASTParser
from ...shared.repo_downloader import RepositoryDownloader
from ...shared.pinecone_embeddings_service import PineconeEmbeddingsService, CodeChunker
from ...shared.relationship_builder import RelationshipBuilder
from ...shared.logger import get_logger

# Import handlers
from .handlers.index_repository import index_repository_handler
from .handlers.embeddings import (
    embed_repository_handler,
    semantic_search_handler,
    get_embeddings_stats_handler,
)
from .handlers.status import (
    get_index_status_handler,
    clear_index_handler,
    clear_embeddings_handler
)

logger = get_logger(__name__)


class IndexerService(BaseMCPServer):
    """MCP Server for repository indexing operations."""
    
    def __init__(self):
        super().__init__(
            service_name="IndexerService",
            host=os.getenv("INDEXER_HOST", "0.0.0.0"),
            port=int(os.getenv("INDEXER_PORT", 8002))
        )
        self.neo4j_service: Neo4jService = None
        self.ast_parser: ASTParser = None
        self.repo_downloader: RepositoryDownloader = None
        self.pinecone_service: PineconeEmbeddingsService = None
        self.code_chunker: CodeChunker = None
        self.relationship_builder: RelationshipBuilder = None
    
    async def register_tools(self):
        """Register indexing tools."""
        
        # Register 9 tools
        tool_definitions = [
            {
                "name": "index_repository",
                "description": "Full repository indexing - clone and parse entire repo",
                "schema": {
                    "type": "object",
                    "properties": {
                        "repo_url": {"type": "string", "description": "GitHub repository URL"},
                        "branch": {"type": "string", "description": "Git branch to index"}
                    },
                    "required": ["repo_url"]
                },
                "handler": lambda **kw: index_repository_handler(
                    repo_url=kw.get("repo_url"),
                    branch=kw.get("branch", "main"),
                    neo4j_service=self.neo4j_service,
                    ast_parser=self.ast_parser,
                    repo_downloader=self.repo_downloader
                )
            },
            {
                "name": "embed_repository",
                "description": "Generate embeddings for repository code and store in Pinecone",
                "schema": {
                    "type": "object",
                    "properties": {
                        "repo_url": {"type": "string", "description": "GitHub repository URL"},
                        "repo_id": {"type": "string", "description": "Repository identifier for Pinecone"},
                        "branch": {"type": "string", "description": "Git branch to embed"}
                    },
                    "required": ["repo_url", "repo_id"]
                },
                "handler": lambda **kw: embed_repository_handler(
                    repo_url=kw.get("repo_url"),
                    repo_id=kw.get("repo_id"),
                    branch=kw.get("branch", "main"),
                    pinecone_service=self.pinecone_service,
                    code_chunker=self.code_chunker,
                    repo_downloader=self.repo_downloader
                )
            },
            {
                "name": "semantic_search",
                "description": "Search code chunks in Pinecone using semantic similarity",
                "schema": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "Search query"},
                        "repo_id": {"type": "string", "description": "Repository ID to search in"},
                        "top_k": {"type": "integer", "description": "Number of results"}
                    },
                    "required": ["query"]
                },
                "handler": lambda **kw: semantic_search_handler(
                    query=kw.get("query"),
                    repo_id=kw.get("repo_id", "all"),
                    top_k=kw.get("top_k", 5),
                    pinecone_service=self.pinecone_service
                )
            },
            {
                "name": "get_embeddings_stats",
                "description": "Get Pinecone embeddings statistics",
                "schema": {
                    "type": "object",
                    "properties": {
                        "repo_id": {"type": "string", "description": "Repository ID"}
                    },
                    "required": []
                },
                "handler": lambda **kw: get_embeddings_stats_handler(
                    repo_id=kw.get("repo_id"),
                    pinecone_service=self.pinecone_service
                )
            },
            {
                "name": "get_index_status",
                "description": "Get Neo4j graph statistics",
                "schema": {"type": "object", "properties": {}, "required": []},
                "handler": lambda **kw: get_index_status_handler(
                    neo4j_service=self.neo4j_service
                )
            },
            {
                "name": "clear_index",
                "description": "Clear all indexed data from Neo4j",
                "schema": {"type": "object", "properties": {}, "required": []},
                "handler": lambda **kw: clear_index_handler(
                    neo4j_service=self.neo4j_service
                )
            },
            {
                "name": "clear_embeddings",
                "description": "Clear all embeddings from Pinecone",
                "schema": {
                    "type": "object",
                    "properties": {
                        "repo_id": {"type": "string", "description": "Repository ID to clear (default: all)"}
                    },
                    "required": []
                },
                "handler": lambda **kw: clear_embeddings_handler(
                    pinecone_service=self.pinecone_service,
                    repo_id=kw.get("repo_id", "all")
                )
            },
        ]
        
        for tool in tool_definitions:
            self.register_tool(
                name=tool["name"],
                description=tool["description"],
                input_schema=tool["schema"],
                handler=tool["handler"]
            )
        
        self.logger.info(f"Registered {len(tool_definitions)} tools")
    
    async def _setup_service(self):
        """Initialize services."""
        try:
            neo4j_uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
            neo4j_user = os.getenv("NEO4J_USER", "neo4j")
            neo4j_password = os.getenv("NEO4J_PASSWORD", "password")
            
            self.neo4j_service = Neo4jService(neo4j_uri, neo4j_user, neo4j_password)
            await self.neo4j_service.verify_connection()
            
            self.ast_parser = ASTParser()
            self.repo_downloader = RepositoryDownloader()
            self.pinecone_service = PineconeEmbeddingsService()
            self.code_chunker = CodeChunker(chunk_size=650, overlap=50)
            self.relationship_builder = RelationshipBuilder()
            
            self.logger.info("✅ Indexer Service initialized successfully")
        except Exception as e:
            self.logger.error(f"❌ Failed to initialize: {e}")
            raise
    
    async def _cleanup_service(self):
        """Cleanup on shutdown."""
        if self.neo4j_service:
            await self.neo4j_service.close()


# ============================================================================
# FASTAPI APP
# ============================================================================

app = FastAPI(title="Indexer Service", version="1.0.0")
indexer_service: IndexerService = None


@app.on_event("startup")
async def startup():
    """Initialize service."""
    global indexer_service
    indexer_service = IndexerService()
    await indexer_service.initialize()


@app.on_event("shutdown")
async def shutdown():
    """Cleanup."""
    if indexer_service:
        await indexer_service.shutdown()


@app.get("/health")
async def health():
    """Health check."""
    if not indexer_service:
        raise HTTPException(status_code=503, detail="Service not initialized")
    
    db_ok = await indexer_service.neo4j_service.verify_connection()
    if not db_ok:
        raise HTTPException(status_code=503, detail="Neo4j connection failed")
    
    return {
        "status": "healthy",
        "service": "IndexerService",
        "neo4j": "ok",
        "tools": len(indexer_service.tools)
    }


@app.get("/tools")
async def get_tools():
    """Get available tools."""
    if not indexer_service:
        raise HTTPException(status_code=503, detail="Service not initialized")
    
    return {
        "service": "IndexerService",
        "tools": indexer_service.get_tools_schema()
    }


@app.post("/execute")
async def execute_tool(tool_name: str, tool_input: Dict[str, Any]):
    """Execute a tool."""
    if not indexer_service:
        raise HTTPException(status_code=503, detail="Service not initialized")
    
    result = await indexer_service.execute_tool(tool_name, tool_input)
    return {
        "success": result.success,
        "data": result.data,
        "error": result.error
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app,
        host=os.getenv("INDEXER_HOST", "0.0.0.0"),
        port=int(os.getenv("INDEXER_PORT", 8002))
    )
