"""
MCP Utilities and Base Types.

WHAT: Core types and utilities for MCP protocol
WHY: Standardized interface for all agents
HOW: Define Tool schema, ToolResult, and agent base class

Example:
    class MyTool(MCPTool):
        name = "my_tool"
        description = "Does something useful"
        
        async def execute(self, param1: str) -> ToolResult:
            return ToolResult(success=True, data={"result": "done"})
"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class ToolParameter(BaseModel):
    """Definition of a tool parameter."""

    name: str
    """Parameter name"""

    description: str
    """Parameter description"""

    type: str
    """Parameter type (string, integer, array, etc.)"""

    required: bool = True
    """Whether parameter is required"""

    default: Optional[Any] = None
    """Default value if not required"""


class ToolDefinition(BaseModel):
    """
    MCP Tool Definition.

    Describes what a tool does and what parameters it accepts.
    """

    name: str
    """Tool name (must be unique within agent)"""

    description: str
    """Tool description"""

    parameters: List[ToolParameter]
    """List of parameters"""

    category: str = "general"
    """Tool category for grouping"""

    async_capable: bool = True
    """Whether tool supports async execution"""


class ToolResult(BaseModel):
    """
    Result of tool execution.

    Returned by all MCP tools.
    """

    success: bool
    """Whether execution succeeded"""

    data: Optional[Dict[str, Any]] = None
    """Tool result data"""

    error: Optional[str] = None
    """Error message if failed"""

    metadata: Optional[Dict[str, Any]] = None
    """Additional metadata"""


class MCPTool(BaseModel):
    """
    Base class for MCP Tools.

    All tools must inherit from this and implement execute method.

    Example:
        class MyTool(MCPTool):
            name = "my_tool"
            description = "Does X"
            
            async def execute(self, **kwargs) -> ToolResult:
                return ToolResult(success=True, data={...})
    """

    name: str
    """Tool name"""

    description: str
    """Tool description"""

    category: str = "general"
    """Tool category"""

    async def execute(self, **kwargs: Any) -> ToolResult:
        """
        Execute the tool.

        Must be implemented by subclasses.

        Args:
            **kwargs: Tool-specific parameters

        Returns:
            ToolResult with success status and data
        """
        raise NotImplementedError("Subclasses must implement execute()")

    def get_definition(self) -> ToolDefinition:
        """
        Get tool definition for MCP protocol.

        Must be implemented by subclasses to describe parameters.

        Returns:
            ToolDefinition
        """
        return ToolDefinition(
            name=self.name,
            description=self.description,
            parameters=[],
            category=self.category,
        )


class AgentConfig(BaseModel):
    """Configuration for an MCP agent."""

    name: str
    """Agent name"""

    host: str = "localhost"
    """Agent host"""

    port: int
    """Agent port"""

    description: str = ""
    """Agent description"""

    version: str = "1.0.0"
    """Agent version"""

    timeout_seconds: int = 30
    """Request timeout"""

    retry_attempts: int = 3
    """Number of retry attempts"""


class AgentInfo(BaseModel):
    """Information about an agent and its tools."""

    name: str
    """Agent name"""

    host: str
    """Agent host"""

    port: int
    """Agent port"""

    description: str
    """Agent description"""

    version: str
    """Agent version"""

    tools: List[ToolDefinition]
    """Available tools"""

    status: str = "healthy"
    """Agent status: healthy, degraded, offline"""


class MCPMessage(BaseModel):
    """
    Message format for MCP protocol.

    Used for agent-to-agent communication.
    """

    message_id: str
    """Unique message ID"""

    sender: str
    """Sending agent name"""

    recipient: str
    """Receiving agent name"""

    tool_name: str
    """Tool to invoke"""

    parameters: Dict[str, Any]
    """Tool parameters"""

    correlation_id: str
    """Correlation ID for tracing"""

    timestamp: str
    """Message timestamp (ISO format)"""


class MCPResponse(BaseModel):
    """
    Response format for MCP protocol.

    Returns result of tool execution.
    """

    message_id: str
    """Corresponding request message ID"""

    sender: str
    """Sending agent name"""

    result: ToolResult
    """Tool execution result"""

    execution_time_ms: float
    """How long execution took"""

    correlation_id: str
    """Correlation ID for tracing"""


class ConversationMessage(BaseModel):
    """
    Message in a conversation.

    Stored in conversation memory.
    """

    role: str
    """Message role: user, assistant, system"""

    content: str
    """Message content"""

    timestamp: str
    """When message was sent (ISO format)"""

    agent_name: Optional[str] = None
    """Which agent generated this (if assistant)"""

    metadata: Optional[Dict[str, Any]] = None
    """Additional metadata"""


class ConversationContext(BaseModel):
    """
    Context for a multi-turn conversation.

    Maintained by orchestrator.
    """

    session_id: str
    """Unique session ID"""

    messages: List[ConversationMessage]
    """Conversation history"""

    user_info: Optional[Dict[str, Any]] = None
    """User information"""

    last_agent_used: Optional[str] = None
    """Last agent that responded"""

    created_at: str
    """When conversation was created (ISO format)"""

    last_updated: str
    """When conversation was last updated (ISO format)"""

    metadata: Optional[Dict[str, Any]] = None
    """Additional metadata"""


class QueryAnalysis(BaseModel):
    """
    Result of query analysis by orchestrator.

    Determines which agents to route query to.
    """

    query: str
    """Original user query"""

    intent: str
    """Identified intent (e.g., 'search', 'analyze', 'explain')"""

    entities: List[str]
    """Extracted entities (class names, function names, etc.)"""

    required_agents: List[str]
    """Agents that should handle this query"""

    context_needed: bool
    """Whether conversation context is needed"""

    follow_up: bool
    """Whether this is a follow-up query"""

    confidence: float
    """Confidence score (0.0 to 1.0)"""