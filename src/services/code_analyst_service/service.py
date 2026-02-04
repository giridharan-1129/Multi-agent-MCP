"""Code Analyst Service - MCP Server for code analysis."""

import os
from typing import Any, Dict, Optional
from ...shared.mcp_server import BaseMCPServer, ToolResult
from ...shared.neo4j_service import Neo4jService
from ...shared.logger import get_logger
from .handlers import (
    analyze_function_handler,
    analyze_class_handler,
    find_patterns_handler,
    get_code_snippet_handler,
    compare_implementations_handler,
    explain_implementation_handler,
)

logger = get_logger(__name__)


class CodeAnalystService(BaseMCPServer):
    """MCP Server for code analysis operations."""
    
    def __init__(self):
        super().__init__(
            service_name="CodeAnalystService",
            host=os.getenv("CODE_ANALYST_HOST", "0.0.0.0"),
            port=int(os.getenv("CODE_ANALYST_PORT", 8004))
        )
        self.neo4j_service: Neo4jService = None
    
    async def register_tools(self):
        """Register code analysis tools."""
        
        # Tool 1: Analyze Function
        self.register_tool(
            name="analyze_function",
            description="Deep analysis of a function's logic and calls",
            input_schema={
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Function name to analyze"
                    }
                },
                "required": ["name"]
            },
            handler=self._analyze_function_wrapper
        )
        
        # Tool 2: Analyze Class
        self.register_tool(
            name="analyze_class",
            description="Comprehensive class analysis including methods and inheritance",
            input_schema={
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Class name to analyze"
                    }
                },
                "required": ["name"]
            },
            handler=self._analyze_class_wrapper
        )
        
        # Tool 3: Find Patterns
        self.register_tool(
            name="find_patterns",
            description="Detect design patterns in code",
            input_schema={
                "type": "object",
                "properties": {
                    "pattern_type": {
                        "type": "string",
                        "description": "Pattern type to search for (e.g., Singleton, Factory, Decorator)"
                    }
                }
            },
            handler=self._find_patterns_wrapper
        )
        
        # Tool 4: Get Code Snippet
        self.register_tool(
            name="get_code_snippet",
            description="Extract code with surrounding context",
            input_schema={
                "type": "object",
                "properties": {
                    "entity_name": {
                        "type": "string",
                        "description": "Entity name to get code for"
                    },
                    "context_lines": {
                        "type": "integer",
                        "description": "Lines of context before/after (default: 5)"
                    }
                },
                "required": ["entity_name"]
            },
            handler=self._get_code_snippet_wrapper
        )
        
        # Tool 5: Compare Implementations
        self.register_tool(
            name="compare_implementations",
            description="Compare two code entities side-by-side",
            input_schema={
                "type": "object",
                "properties": {
                    "entity1": {
                        "type": "string",
                        "description": "First entity name"
                    },
                    "entity2": {
                        "type": "string",
                        "description": "Second entity name"
                    }
                },
                "required": ["entity1", "entity2"]
            },
            handler=self._compare_implementations_wrapper
        )
        
        # Tool 6: Explain Implementation
        self.register_tool(
            name="explain_implementation",
            description="Generate explanation of how code works",
            input_schema={
                "type": "object",
                "properties": {
                    "entity_name": {
                        "type": "string",
                        "description": "Entity name to explain"
                    }
                },
                "required": ["entity_name"]
            },
            handler=self._explain_implementation_wrapper
        )
        
        self.logger.info("Registered 6 code analysis tools")
    
    async def _setup_service(self):
        """Initialize Neo4j service."""
        try:
            neo4j_uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
            neo4j_user = os.getenv("NEO4J_USER", "neo4j")
            neo4j_password = os.getenv("NEO4J_PASSWORD", "password")
            
            self.neo4j_service = Neo4jService(neo4j_uri, neo4j_user, neo4j_password)
            await self.neo4j_service.verify_connection()
            
            self.logger.info("Code Analyst Service initialized successfully")
        except Exception as e:
            self.logger.error(f"Failed to initialize code analyst service: {e}")
            raise
    
    # ============================================================================
    # WRAPPER METHODS (delegate to handlers)
    # ============================================================================
    
    async def _analyze_function_wrapper(self, name: str) -> ToolResult:
        """Wrapper for analyze_function handler."""
        return await analyze_function_handler(self.neo4j_service, name)
    
    async def _analyze_class_wrapper(self, name: str) -> ToolResult:
        """Wrapper for analyze_class handler."""
        return await analyze_class_handler(self.neo4j_service, name)
    
    async def _find_patterns_wrapper(self, pattern_type: Optional[str] = None) -> ToolResult:
        """Wrapper for find_patterns handler."""
        return await find_patterns_handler(self.neo4j_service, pattern_type)
    
    async def _get_code_snippet_wrapper(
        self,
        entity_name: str,
        context_lines: int = 5
    ) -> ToolResult:
        """Wrapper for get_code_snippet handler."""
        return await get_code_snippet_handler(self.neo4j_service, entity_name, context_lines)
    
    async def _compare_implementations_wrapper(
        self,
        entity1: str,
        entity2: str
    ) -> ToolResult:
        """Wrapper for compare_implementations handler."""
        return await compare_implementations_handler(self.neo4j_service, entity1, entity2)
    
    async def _explain_implementation_wrapper(self, entity_name: str) -> ToolResult:
        """Wrapper for explain_implementation handler."""
        return await explain_implementation_handler(self.neo4j_service, entity_name)
    
    async def _cleanup_service(self):
        """Cleanup Neo4j connection."""
        if self.neo4j_service:
            await self.neo4j_service.close()
