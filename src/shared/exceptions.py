"""
Custom Exceptions for Multi-Agent System.

WHAT: Exception hierarchy for the entire system
WHY: Consistent, typed error handling across agents
HOW: Base exception + specialized exceptions for different failure modes

Example:
    try:
        result = await graph_agent.query()
    except AgentTimeoutError:
        logger.error("Agent took too long")
    except Neo4jError as e:
        logger.error(f"Database error: {e}")
"""


class MCPException(Exception):
    """
    Base exception for MCP multi-agent system.

    All other exceptions inherit from this.
    """

    pass


# ========================
# Agent Exceptions
# ========================


class AgentError(MCPException):
    """Base exception for agent-related errors."""

    pass


class AgentTimeoutError(AgentError):
    """Raised when agent request times out."""

    def __init__(self, agent_name: str, timeout_seconds: int):
        """
        Initialize AgentTimeoutError.

        Args:
            agent_name: Name of the agent that timed out
            timeout_seconds: Timeout duration
        """
        self.agent_name = agent_name
        self.timeout_seconds = timeout_seconds
        super().__init__(
            f"Agent '{agent_name}' timed out after {timeout_seconds} seconds"
        )


class AgentConnectionError(AgentError):
    """Raised when cannot connect to agent."""

    def __init__(self, agent_name: str, error_detail: str):
        """
        Initialize AgentConnectionError.

        Args:
            agent_name: Name of the agent
            error_detail: Details about connection failure
        """
        self.agent_name = agent_name
        self.error_detail = error_detail
        super().__init__(
            f"Failed to connect to agent '{agent_name}': {error_detail}"
        )


class AgentExecutionError(AgentError):
    """Raised when agent execution fails."""

    def __init__(self, agent_name: str, tool_name: str, error_detail: str):
        """
        Initialize AgentExecutionError.

        Args:
            agent_name: Name of the agent
            tool_name: Name of the tool that failed
            error_detail: Details about the failure
        """
        self.agent_name = agent_name
        self.tool_name = tool_name
        self.error_detail = error_detail
        super().__init__(
            f"Agent '{agent_name}' tool '{tool_name}' failed: {error_detail}"
        )


class OrchestratorError(MCPException):
    """Raised when orchestrator fails."""

    pass


class QueryRoutingError(OrchestratorError):
    """Raised when orchestrator cannot route query."""

    pass


# ========================
# Database Exceptions
# ========================


class DatabaseError(MCPException):
    """Base exception for database errors."""

    pass


class Neo4jError(DatabaseError):
    """Raised when Neo4j operation fails."""

    def __init__(self, query: str, error_detail: str):
        """
        Initialize Neo4jError.

        Args:
            query: The query that failed
            error_detail: Details about the failure
        """
        self.query = query
        self.error_detail = error_detail
        super().__init__(f"Neo4j query failed: {error_detail}\nQuery: {query}")


class Neo4jConnectionError(DatabaseError):
    """Raised when cannot connect to Neo4j."""

    def __init__(self, uri: str, error_detail: str):
        """
        Initialize Neo4jConnectionError.

        Args:
            uri: Neo4j connection URI
            error_detail: Details about connection failure
        """
        self.uri = uri
        self.error_detail = error_detail
        super().__init__(f"Cannot connect to Neo4j at {uri}: {error_detail}")


# ========================
# Repository Exceptions
# ========================


class RepositoryError(MCPException):
    """Base exception for repository operations."""

    pass


class RepositoryCloneError(RepositoryError):
    """Raised when cloning repository fails."""

    def __init__(self, repo_url: str, error_detail: str):
        """
        Initialize RepositoryCloneError.

        Args:
            repo_url: URL of repository to clone
            error_detail: Details about the failure
        """
        self.repo_url = repo_url
        self.error_detail = error_detail
        super().__init__(f"Failed to clone {repo_url}: {error_detail}")


class RepositoryIndexingError(RepositoryError):
    """Raised when indexing repository fails."""

    def __init__(self, repo_path: str, error_detail: str):
        """
        Initialize RepositoryIndexingError.

        Args:
            repo_path: Path to repository
            error_detail: Details about the failure
        """
        self.repo_path = repo_path
        self.error_detail = error_detail
        super().__init__(f"Failed to index {repo_path}: {error_detail}")


class FileParsingError(RepositoryError):
    """Raised when parsing file fails."""

    def __init__(self, file_path: str, error_detail: str):
        """
        Initialize FileParsingError.

        Args:
            file_path: Path to file that failed to parse
            error_detail: Details about the failure
        """
        self.file_path = file_path
        self.error_detail = error_detail
        super().__init__(f"Failed to parse {file_path}: {error_detail}")


# ========================
# Code Analysis Exceptions
# ========================


class CodeAnalysisError(MCPException):
    """Base exception for code analysis errors."""

    pass


class EntityNotFoundError(CodeAnalysisError):
    """Raised when entity not found in codebase."""

    def __init__(self, entity_type: str, entity_name: str):
        """
        Initialize EntityNotFoundError.

        Args:
            entity_type: Type of entity (class, function, etc.)
            entity_name: Name of entity
        """
        self.entity_type = entity_type
        self.entity_name = entity_name
        super().__init__(
            f"Could not find {entity_type} named '{entity_name}' in codebase"
        )


class PatternAnalysisError(CodeAnalysisError):
    """Raised when pattern analysis fails."""

    pass


# ========================
# Validation Exceptions
# ========================


class ValidationError(MCPException):
    """Raised when input validation fails."""

    def __init__(self, field: str, error_detail: str):
        """
        Initialize ValidationError.

        Args:
            field: Field that failed validation
            error_detail: Details about the validation failure
        """
        self.field = field
        self.error_detail = error_detail
        super().__init__(f"Validation failed for field '{field}': {error_detail}")


# ========================
# LLM Exceptions
# ========================


class LLMError(MCPException):
    """Base exception for LLM-related errors."""

    pass


class LLMRateLimitError(LLMError):
    """Raised when hitting rate limits."""

    pass


class LLMAuthenticationError(LLMError):
    """Raised when authentication fails."""

    pass


class LLMGenerationError(LLMError):
    """Raised when text generation fails."""

    def __init__(self, model: str, error_detail: str):
        """
        Initialize LLMGenerationError.

        Args:
            model: Model that failed
            error_detail: Details about the failure
        """
        self.model = model
        self.error_detail = error_detail
        super().__init__(f"LLM generation failed with {model}: {error_detail}")