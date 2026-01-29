"""
Base Agent Class for MCP System.

WHAT: Foundation class for all MCP agents
WHY: Provides common functionality and interface for all agents
HOW: Defines tools, health checks, agent info, message handling

Example:
    class MyAgent(BaseAgent):
        name = "my_agent"
        description = "Does something useful"
        
        def __init__(self):
            super().__init__()
            self.register_tool(MyTool())
        
        async def startup(self):
            await super().startup()
            # Custom startup logic
"""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import uuid4

from .exceptions import AgentExecutionError, AgentError
from .logger import get_logger
from .mcp_types import (
    AgentInfo,
    MCPMessage,
    MCPResponse,
    ToolDefinition,
    ToolResult,
    MCPTool,
)

logger = get_logger(__name__)


class BaseAgent(ABC):
    """
    Base class for all MCP agents.

    Provides common functionality including tool management, health checks,
    message handling, and agent metadata.

    Attributes:
        name: Agent name
        description: Agent description
        version: Agent version
        tools: Dict of registered tools
        is_healthy: Agent health status
        start_time: When agent started
    """

    # These should be overridden by subclasses
    name: str = "base_agent"
    description: str = "Base agent"
    version: str = "1.0.0"

    def __init__(self):
        """Initialize base agent."""
        self.tools: Dict[str, MCPTool] = {}
        self.is_healthy = False
        self.start_time: Optional[datetime] = None
        self.request_count = 0
        self.error_count = 0

        logger.info(
            "Agent initialized",
            name=self.name,
            description=self.description,
            version=self.version,
        )

    async def startup(self) -> None:
        """
        Start the agent.

        Called when agent starts up. Override in subclasses for custom logic.
        """
        self.is_healthy = True
        self.start_time = datetime.utcnow()
        logger.info("Agent started", name=self.name)

    async def shutdown(self) -> None:
        """
        Shut down the agent.

        Called when agent shuts down. Override in subclasses for cleanup.
        """
        self.is_healthy = False
        logger.info("Agent shut down", name=self.name)

    def register_tool(self, tool: MCPTool) -> None:
        """
        Register a tool with this agent.

        Args:
            tool: MCPTool instance to register
        """
        self.tools[tool.name] = tool
        logger.debug("Tool registered", agent=self.name, tool=tool.name)

    async def execute_tool(
        self,
        tool_name: str,
        parameters: Dict[str, Any],
    ) -> ToolResult:
        """
        Execute a tool.

        Args:
            tool_name: Name of tool to execute
            parameters: Tool parameters

        Returns:
            ToolResult with execution result

        Raises:
            AgentExecutionError: If tool not found or execution fails
        """
        self.request_count += 1

        if tool_name not in self.tools:
            self.error_count += 1
            error_msg = f"Tool '{tool_name}' not found"
            logger.error("Tool not found", agent=self.name, tool=tool_name)
            raise AgentExecutionError(
                agent_name=self.name,
                tool_name=tool_name,
                error_detail=error_msg,
            )

        try:
            tool = self.tools[tool_name]
            result = await tool.execute(**parameters)
            
            if result.success:
                logger.info(
                    "Tool executed successfully",
                    agent=self.name,
                    tool=tool_name,
                )
            else:
                self.error_count += 1
                logger.error(
                    "Tool execution failed",
                    agent=self.name,
                    tool=tool_name,
                    error=result.error,
                )

            return result

        except Exception as e:
            self.error_count += 1
            logger.error(
                "Tool execution error",
                agent=self.name,
                tool=tool_name,
                error=str(e),
            )
            raise AgentExecutionError(
                agent_name=self.name,
                tool_name=tool_name,
                error_detail=str(e),
            )

    async def process_message(self, message: MCPMessage) -> MCPResponse:
        """
        Process an incoming MCP message.

        Args:
            message: MCP message to process

        Returns:
            MCPResponse with result

        Raises:
            AgentExecutionError: If processing fails
        """
        logger.info(
            "Processing message",
            agent=self.name,
            tool=message.tool_name,
            correlation_id=message.correlation_id,
        )

        try:
            # Execute the tool
            result = await self.execute_tool(
                message.tool_name,
                message.parameters,
            )

            # Create response
            response = MCPResponse(
                message_id=message.message_id,
                sender=self.name,
                result=result,
                execution_time_ms=0.0,  # Would track actual time
                correlation_id=message.correlation_id,
            )

            return response

        except Exception as e:
            # Return error result
            error_result = ToolResult(
                success=False,
                error=str(e),
            )

            return MCPResponse(
                message_id=message.message_id,
                sender=self.name,
                result=error_result,
                execution_time_ms=0.0,
                correlation_id=message.correlation_id,
            )

    def get_info(self) -> AgentInfo:
        """
        Get agent information.

        Returns:
            AgentInfo with agent metadata and tools
        """
        tools = [tool.get_definition() for tool in self.tools.values()]

        status = "healthy" if self.is_healthy else "offline"

        info = AgentInfo(
            name=self.name,
            host="localhost",  # Would be set from config
            port=8000,  # Would be set from config
            description=self.description,
            version=self.version,
            tools=tools,
            status=status,
        )

        return info

    async def health_check(self) -> Dict[str, Any]:
        """
        Perform health check.

        Override in subclasses for custom health checks.

        Returns:
            Health check result
        """
        uptime = (datetime.utcnow() - self.start_time).total_seconds() if self.start_time else 0

        health = {
            "name": self.name,
            "status": "healthy" if self.is_healthy else "unhealthy",
            "uptime_seconds": uptime,
            "request_count": self.request_count,
            "error_count": self.error_count,
            "tools_registered": len(self.tools),
        }

        logger.debug("Health check performed", health=health)
        return health

    def list_tools(self) -> List[Dict[str, Any]]:
        """
        List all registered tools.

        Returns:
            List of tool definitions
        """
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "category": tool.category,
            }
            for tool in self.tools.values()
        ]

    def get_tool(self, tool_name: str) -> Optional[MCPTool]:
        """
        Get a specific tool.

        Args:
            tool_name: Name of tool

        Returns:
            MCPTool if found, None otherwise
        """
        return self.tools.get(tool_name)

    @abstractmethod
    async def initialize(self) -> None:
        """
        Initialize agent-specific resources.

        Must be implemented by subclasses.
        """
        pass
