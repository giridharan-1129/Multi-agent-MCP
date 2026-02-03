"""
Base MCP Server Class - Reusable async MCP server for all services.

Handles:
- MCP protocol implementation
- Tool registration and execution
- Error handling and logging
- Health checks
- Graceful shutdown
"""

import asyncio
import json
from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, List, Optional
from dataclasses import dataclass, asdict
import logging

from .logger import get_logger
from .exceptions import MCPServerError

logger = get_logger(__name__)


@dataclass
class ToolDefinition:
    """MCP Tool definition."""
    name: str
    description: str
    inputSchema: Dict[str, Any]


@dataclass
class ToolResult:
    """Tool execution result."""
    success: bool
    data: Optional[Any] = None
    error: Optional[str] = None


class BaseMCPServer(ABC):
    """
    Base class for all MCP servers.
    
    Subclasses implement:
    - register_tools(): Define available tools
    - execute_tool(): Execute tool by name
    """
    
    def __init__(self, service_name: str, host: str = "localhost", port: int = 8000):
        self.service_name = service_name
        self.host = host
        self.port = port
        self.tools: Dict[str, ToolDefinition] = {}
        self.tool_handlers: Dict[str, Callable] = {}
        self.is_running = False
        self.logger = get_logger(service_name)
        
    async def initialize(self):
        """Initialize the server - register tools, connect to services."""
        self.logger.info(f"Initializing {self.service_name}")
        await self.register_tools()
        await self._setup_service()
        self.logger.info(f"{self.service_name} initialized")
    
    @abstractmethod
    async def register_tools(self):
        """
        Register available tools.
        
        Subclasses must implement:
        
        async def register_tools(self):
            self.register_tool(
                name="my_tool",
                description="What it does",
                input_schema={...},
                handler=self.my_tool_handler
            )
        """
        pass
    
    @abstractmethod
    async def _setup_service(self):
        """Setup service-specific connections (Neo4j, Redis, etc)."""
        pass
    
    def register_tool(
        self,
        name: str,
        description: str,
        input_schema: Dict[str, Any],
        handler: Callable
    ):
        """Register a tool with its handler."""
        self.tools[name] = ToolDefinition(
            name=name,
            description=description,
            inputSchema=input_schema
        )
        self.tool_handlers[name] = handler
        self.logger.debug(f"Registered tool: {name}")
    
    async def execute_tool(self, tool_name: str, tool_input: Dict[str, Any]) -> ToolResult:
        """Execute a tool by name."""
        if tool_name not in self.tool_handlers:
            return ToolResult(
                success=False,
                error=f"Tool not found: {tool_name}"
            )
        
        try:
            handler = self.tool_handlers[tool_name]
            result = await handler(**tool_input)
            
            if isinstance(result, ToolResult):
                return result
            else:
                return ToolResult(success=True, data=result)
        
        except Exception as e:
            self.logger.error(f"Tool execution failed: {tool_name}", exc_info=True)
            return ToolResult(
                success=False,
                error=str(e)
            )
    
    def get_tools_schema(self) -> List[Dict[str, Any]]:
        """Get MCP-format tool schemas."""
        return [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.inputSchema
                }
            }
            for tool in self.tools.values()
        ]
    
    async def health_check(self) -> Dict[str, Any]:
        """Health check endpoint response."""
        return {
            "status": "healthy",
            "service": self.service_name,
            "tools_available": len(self.tools)
        }
    
    async def shutdown(self):
        """Graceful shutdown."""
        self.logger.info(f"Shutting down {self.service_name}")
        self.is_running = False
        await self._cleanup_service()
        self.logger.info(f"{self.service_name} shutdown complete")
    
    @abstractmethod
    async def _cleanup_service(self):
        """Cleanup service-specific resources."""
        pass