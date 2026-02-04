"""Graph Query Service - MCP Server for Neo4j operations."""

import os
from typing import Any, Dict

from ...shared.mcp_server import BaseMCPServer, ToolResult
from ...shared.neo4j_service import Neo4jService
from ...shared.logger import get_logger
from .handlers import (
    find_entity_handler,
    get_dependencies_handler,
    get_dependents_handler,
    trace_imports_handler,
    find_related_handler,
    execute_query_handler,
)

logger = get_logger(__name__)


class GraphQueryService(BaseMCPServer):
    """MCP Server for graph database operations."""
    
    def __init__(self):
        super().__init__(
            service_name="GraphQueryService",
            host=os.getenv("GRAPH_QUERY_HOST", "0.0.0.0"),
            port=int(os.getenv("GRAPH_QUERY_PORT", 8003))
        )
        self.neo4j_service: Neo4jService = None
    
    async def register_tools(self):
        """Register graph query tools."""
        
        # Tool 1: Find Entity
        self.register_tool(
            name="find_entity",
            description="Find a class, function, or module by name",
            input_schema={
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Entity name to search for"
                    },
                    "entity_type": {
                        "type": "string",
                        "enum": ["Class", "Function", "Module"],
                        "description": "Optional filter by entity type"
                    }
                },
                "required": ["name"]
            },
            handler=self._find_entity_wrapper
        )
        
        # Tool 2: Get Dependencies
        self.register_tool(
            name="get_dependencies",
            description="Find what an entity depends on",
            input_schema={
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Entity name to analyze"
                    }
                },
                "required": ["name"]
            },
            handler=self._get_dependencies_wrapper
        )
        
        # Tool 3: Get Dependents
        self.register_tool(
            name="get_dependents",
            description="Find what depends on an entity (who uses it)",
            input_schema={
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Entity name to analyze"
                    }
                },
                "required": ["name"]
            },
            handler=self._get_dependents_wrapper
        )
        
        # Tool 4: Trace Imports
        self.register_tool(
            name="trace_imports",
            description="Follow import chain for a module",
            input_schema={
                "type": "object",
                "properties": {
                    "module_name": {
                        "type": "string",
                        "description": "Module name to trace"
                    }
                },
                "required": ["module_name"]
            },
            handler=self._trace_imports_wrapper
        )
        
        # Tool 5: Find Related
        self.register_tool(
            name="find_related",
            description="Get entities related by specified relationship type",
            input_schema={
                "type": "object",
                "properties": {
                    "entity_name": {
                        "type": "string",
                        "description": "Starting entity name"
                    },
                    "relationship_type": {
                        "type": "string",
                        "description": "Relationship type (e.g., CALLS, INHERITS_FROM)"
                    },
                    "direction": {
                        "type": "string",
                        "enum": ["outgoing", "incoming", "both"],
                        "description": "Relationship direction"
                    }
                },
                "required": ["entity_name", "relationship_type"]
            },
            handler=self._find_related_wrapper
        )
        
        # Tool 6: Execute Custom Query
        self.register_tool(
            name="execute_query",
            description="Execute custom Cypher query (read-only, with safety checks)",
            input_schema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Cypher query to execute"
                    },
                    "parameters": {
                        "type": "object",
                        "description": "Query parameters"
                    }
                },
                "required": ["query"]
            },
            handler=self._execute_query_wrapper
        )
        
        self.logger.info("Registered 6 graph query tools")
    
    async def _setup_service(self):
        """Initialize Neo4j service."""
        try:
            neo4j_uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
            neo4j_user = os.getenv("NEO4J_USER", "neo4j")
            neo4j_password = os.getenv("NEO4J_PASSWORD", "password")
            
            self.neo4j_service = Neo4jService(neo4j_uri, neo4j_user, neo4j_password)
            await self.neo4j_service.verify_connection()
            
            self.logger.info("Graph Query Service initialized successfully")
        except Exception as e:
            self.logger.error(f"Failed to initialize graph query service: {e}")
            raise
    
    # ============================================================================
    # WRAPPER METHODS (delegate to handlers)
    # ============================================================================
    
    async def _find_entity_wrapper(self, name: str, entity_type: str = None) -> ToolResult:
        """Wrapper for find_entity handler."""
        return await find_entity_handler(self.neo4j_service, name, entity_type)
    
    async def _get_dependencies_wrapper(self, name: str) -> ToolResult:
        """Wrapper for get_dependencies handler."""
        return await get_dependencies_handler(self.neo4j_service, name)
    
    async def _get_dependents_wrapper(self, name: str) -> ToolResult:
        """Wrapper for get_dependents handler."""
        return await get_dependents_handler(self.neo4j_service, name)
    
    async def _trace_imports_wrapper(self, module_name: str) -> ToolResult:
        """Wrapper for trace_imports handler."""
        return await trace_imports_handler(self.neo4j_service, module_name)
    
    async def _find_related_wrapper(
        self,
        entity_name: str,
        relationship_type: str,
        direction: str = "outgoing"
    ) -> ToolResult:
        """Wrapper for find_related handler."""
        return await find_related_handler(self.neo4j_service, entity_name, relationship_type, direction)
    
    async def _execute_query_wrapper(
        self,
        query: str,
        parameters: Dict[str, Any] = None
    ) -> ToolResult:
        """Wrapper for execute_query handler."""
        return await execute_query_handler(self.neo4j_service, query, parameters)
    
    async def _cleanup_service(self):
        """Cleanup Neo4j connection."""
        if self.neo4j_service:
            await self.neo4j_service.close()
