"""
Shared Module - Common utilities for all agents.

Exports:
    - config: Centralized configuration
    - logger: Structured logging
    - exceptions: Custom exception types
    - mcp_types: MCP protocol types
"""

from .config import Config, config
from .exceptions import (
    AgentConnectionError,
    AgentError,
    AgentExecutionError,
    AgentTimeoutError,
    CodeAnalysisError,
    DatabaseError,
    EntityNotFoundError,
    FileParsingError,
    LLMAuthenticationError,
    LLMError,
    LLMGenerationError,
    LLMRateLimitError,
    MCPException,
    Neo4jConnectionError,
    Neo4jError,
    OrchestratorError,
    PatternAnalysisError,
    QueryRoutingError,
    RepositoryCloneError,
    RepositoryError,
    RepositoryIndexingError,
    ValidationError,
)
from .logger import (
    configure_logging,
    generate_correlation_id,
    get_correlation_id,
    get_logger,
    set_correlation_id,
)
from .mcp_types import (
    AgentConfig,
    AgentInfo,
    ConversationContext,
    ConversationMessage,
    MCPMessage,
    MCPResponse,
    MCPTool,
    QueryAnalysis,
    ToolDefinition,
    ToolParameter,
    ToolResult,
)

__all__ = [
    # Config
    "Config",
    "config",
    # Logger
    "get_logger",
    "configure_logging",
    "get_correlation_id",
    "set_correlation_id",
    "generate_correlation_id",
    # Exceptions
    "MCPException",
    "AgentError",
    "AgentTimeoutError",
    "AgentConnectionError",
    "AgentExecutionError",
    "OrchestratorError",
    "QueryRoutingError",
    "DatabaseError",
    "Neo4jError",
    "Neo4jConnectionError",
    "RepositoryError",
    "RepositoryCloneError",
    "RepositoryIndexingError",
    "FileParsingError",
    "CodeAnalysisError",
    "EntityNotFoundError",
    "PatternAnalysisError",
    "ValidationError",
    "LLMError",
    "LLMRateLimitError",
    "LLMAuthenticationError",
    "LLMGenerationError",
    # MCP Types
    "MCPTool",
    "ToolDefinition",
    "ToolParameter",
    "ToolResult",
    "AgentConfig",
    "AgentInfo",
    "MCPMessage",
    "MCPResponse",
    "ConversationMessage",
    "ConversationContext",
    "QueryAnalysis",
]