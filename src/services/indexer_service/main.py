"""
Indexer Service - MCP Server for repository indexing and AST parsing.

Responsibilities:
- Clone and parse repositories
- Extract AST information from Python files
- Identify classes, functions, and relationships
- Populate Neo4j knowledge graph
- Handle incremental updates
"""

import os
import asyncio
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException

from ...shared.mcp_server import BaseMCPServer, ToolResult
from ...shared.neo4j_service import Neo4jService
from ...shared.ast_parser import ASTParser
from ...shared.repo_downloader import RepositoryDownloader
from ...shared.logger import get_logger

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
    
    async def register_tools(self):
        """Register indexing tools."""
        
        # Tool 1: Index Repository
        self.register_tool(
            name="index_repository",
            description="Full repository indexing - clone and parse entire repo",
            input_schema={
                "type": "object",
                "properties": {
                    "repo_url": {
                        "type": "string",
                        "description": "GitHub repository URL"
                    },
                    "branch": {
                        "type": "string",
                        "description": "Git branch to index (default: main)"
                    }
                },
                "required": ["repo_url"]
            },
            handler=self.index_repository_handler
        )
        
        # Tool 2: Index File
        self.register_tool(
            name="index_file",
            description="Index a single Python file",
            input_schema={
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Path to Python file"
                    },
                    "file_content": {
                        "type": "string",
                        "description": "Python file content"
                    }
                },
                "required": ["file_path", "file_content"]
            },
            handler=self.index_file_handler
        )
        
        # Tool 3: Parse Python AST
        self.register_tool(
            name="parse_python_ast",
            description="Parse Python code and extract AST information",
            input_schema={
                "type": "object",
                "properties": {
                    "code": {
                        "type": "string",
                        "description": "Python code to parse"
                    },
                    "file_path": {
                        "type": "string",
                        "description": "File path for context"
                    }
                },
                "required": ["code"]
            },
            handler=self.parse_python_ast_handler
        )
        
        # Tool 4: Extract Entities
        self.register_tool(
            name="extract_entities",
            description="Extract code entities and their relationships",
            input_schema={
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "File path to extract from"
                    }
                },
                "required": ["file_path"]
            },
            handler=self.extract_entities_handler
        )
        
        # Tool 5: Get Index Status
        self.register_tool(
            name="get_index_status",
            description="Get current indexing status and statistics",
            input_schema={
                "type": "object",
                "properties": {}
            },
            handler=self.get_index_status_handler
        )
        
        # Tool 6: Clear Index
        self.register_tool(
            name="clear_index",
            description="Clear all indexed data from the knowledge graph",
            input_schema={
                "type": "object",
                "properties": {}
            },
            handler=self.clear_index_handler
        )
        
        self.logger.info("Registered 6 indexing tools")
    
    async def _setup_service(self):
        """Initialize Neo4j and indexing services."""
        try:
            neo4j_uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
            neo4j_user = os.getenv("NEO4J_USER", "neo4j")
            neo4j_password = os.getenv("NEO4J_PASSWORD", "password")
            
            self.neo4j_service = Neo4jService(neo4j_uri, neo4j_user, neo4j_password)
            await self.neo4j_service.verify_connection()
            
            self.ast_parser = ASTParser()
            self.repo_downloader = RepositoryDownloader()
            
            self.logger.info("Indexer Service initialized successfully")
        except Exception as e:
            self.logger.error(f"Failed to initialize indexer service: {e}")
            raise
    
    # ============================================================================
    # TOOL HANDLERS
    # ============================================================================
    
    async def index_repository_handler(
        self,
        repo_url: str,
        branch: str = "main"
    ) -> ToolResult:
        """Handle index_repository tool."""
        try:
            self.logger.info(f"Starting repository indexing: {repo_url}")
            
            # Download repository
            repo_path = await self.repo_downloader.download(repo_url, branch)
            
            # Index all Python files
            py_files = self.repo_downloader.find_python_files(repo_path)
            self.logger.info(f"Found {len(py_files)} Python files")
            
            stats = {
                "files_indexed": 0,
                "classes": 0,
                "functions": 0,
                "relationships": 0
            }
            
            for py_file in py_files:
                try:
                    with open(py_file, 'r', encoding='utf-8') as f:
                        content = f.read()
                    
                    # Parse and extract entities
                    ast_data = self.ast_parser.parse(content, py_file)
                    
                    # Store in Neo4j
                    await self.neo4j_service.index_file(py_file, ast_data)
                    
                    stats["files_indexed"] += 1
                    stats["classes"] += len(ast_data.get("classes", []))
                    stats["functions"] += len(ast_data.get("functions", []))
                    
                except Exception as e:
                    self.logger.error(f"Failed to index file {py_file}: {e}")
                    continue
            
            self.logger.info(f"Repository indexing complete: {stats}")
            
            return ToolResult(
                success=True,
                data={
                    "repo_url": repo_url,
                    "branch": branch,
                    "repo_path": repo_path,
                    "statistics": stats
                }
            )
        except Exception as e:
            self.logger.error(f"Failed to index repository: {e}")
            return ToolResult(success=False, error=str(e))
    
    async def index_file_handler(
        self,
        file_path: str,
        file_content: str
    ) -> ToolResult:
        """Handle index_file tool."""
        try:
            # Parse file
            ast_data = self.ast_parser.parse(file_content, file_path)
            
            # Store in Neo4j
            await self.neo4j_service.index_file(file_path, ast_data)
            
            self.logger.info(f"Indexed file: {file_path}")
            
            return ToolResult(
                success=True,
                data={
                    "file_path": file_path,
                    "entities": len(ast_data.get("classes", [])) + len(ast_data.get("functions", []))
                }
            )
        except Exception as e:
            self.logger.error(f"Failed to index file: {e}")
            return ToolResult(success=False, error=str(e))
    
    async def parse_python_ast_handler(
        self,
        code: str,
        file_path: str = "unknown.py"
    ) -> ToolResult:
        """Handle parse_python_ast tool."""
        try:
            ast_data = self.ast_parser.parse(code, file_path)
            
            return ToolResult(
                success=True,
                data={
                    "file_path": file_path,
                    "ast": ast_data
                }
            )
        except Exception as e:
            self.logger.error(f"Failed to parse AST: {e}")
            return ToolResult(success=False, error=str(e))
    
    async def extract_entities_handler(self, file_path: str) -> ToolResult:
        """Handle extract_entities tool."""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            ast_data = self.ast_parser.parse(content, file_path)
            
            entities = {
                "classes": ast_data.get("classes", []),
                "functions": ast_data.get("functions", []),
                "imports": ast_data.get("imports", []),
                "relationships": ast_data.get("relationships", [])
            }
            
            return ToolResult(
                success=True,
                data={
                    "file_path": file_path,
                    "entities": entities
                }
            )
        except Exception as e:
            self.logger.error(f"Failed to extract entities: {e}")
            return ToolResult(success=False, error=str(e))
    
    async def get_index_status_handler(self) -> ToolResult:
        """Handle get_index_status tool."""
        try:
            stats = await self.neo4j_service.get_statistics()
            
            return ToolResult(
                success=True,
                data={
                    "status": "indexed",
                    "statistics": stats
                }
            )
        except Exception as e:
            self.logger.error(f"Failed to get index status: {e}")
            return ToolResult(success=False, error=str(e))
    
    async def clear_index_handler(self) -> ToolResult:
        """Handle clear_index tool."""
        try:
            # Clear all nodes from Neo4j
            query = "MATCH (n) DETACH DELETE n"
            await self.neo4j_service.execute_query(query, {})
            
            self.logger.info("Cleared knowledge graph")
            
            return ToolResult(
                success=True,
                data={"status": "cleared"}
            )
        except Exception as e:
            self.logger.error(f"Failed to clear index: {e}")
            return ToolResult(success=False, error=str(e))
    
    async def _cleanup_service(self):
        """Cleanup services."""
        if self.neo4j_service:
            await self.neo4j_service.close()


# ============================================================================
# FASTAPI APP
# ============================================================================

app = FastAPI(title="Indexer Service", version="1.0.0")
indexer_service: IndexerService = None


@app.on_event("startup")
async def startup():
    """Initialize indexer service."""
    global indexer_service
    indexer_service = IndexerService()
    await indexer_service.initialize()


@app.on_event("shutdown")
async def shutdown():
    """Cleanup on shutdown."""
    if indexer_service:
        await indexer_service.shutdown()


@app.get("/health")
async def health():
    """Health check endpoint."""
    if not indexer_service:
        raise HTTPException(status_code=503, detail="Service not initialized")
    
    db_healthy = await indexer_service.neo4j_service.verify_connection()
    
    if not db_healthy:
        raise HTTPException(status_code=503, detail="Neo4j connection failed")
    
    return {
        "status": "healthy",
        "service": "IndexerService",
        "neo4j": "ok",
        "tools": len(indexer_service.tools)
    }


@app.get("/tools")
async def get_tools():
    """Get available tools schema."""
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
    return result.dict()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app,
        host=os.getenv("INDEXER_HOST", "0.0.0.0"),
        port=int(os.getenv("INDEXER_PORT", 8002))
    )
