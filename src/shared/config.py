"""
Shared Configuration Module.

WHAT: Central configuration for all agents and gateway
WHY: Single source of truth for settings, secrets, and credentials
HOW: Pydantic Settings loads from environment variables with type safety

Example:
    config = Config()
    print(config.neo4j_uri)  # Loaded from environment
    print(config.openai_api_key)  # Loaded from environment
"""

from typing import Literal
from pydantic_settings import BaseSettings, SettingsConfigDict




class Neo4jConfig(BaseSettings):
    """Neo4j database configuration."""

    uri: str = "bolt://localhost:7687"
    """Neo4j connection URI"""

    username: str = "neo4j"
    """Neo4j username"""

    password: str = "password"
    """Neo4j password"""

    database: str = "neo4j"
    """Default database name"""

    class Config:
        """Pydantic config."""

        env_prefix = "NEO4J_"


class OpenAIConfig(BaseSettings):
    """OpenAI configuration."""

    api_key: str = ""
    """OpenAI API key"""

    model: str = "gpt-4"
    """Default model to use"""

    temperature: float = 0.7
    """Response temperature (0.0 to 1.0)"""

    max_tokens: int = 2000
    """Maximum tokens in response"""

    class Config:
        """Pydantic config."""

        env_prefix = "OPENAI_"


class MCPServerConfig(BaseSettings):
    """MCP Server configuration."""

    host: str = "localhost"
    """MCP server host"""

    port: int = 8000
    """MCP server port"""

    timeout: int = 30
    """Request timeout in seconds"""

    retry_attempts: int = 3
    """Number of retry attempts"""

    class Config:
        """Pydantic config."""

        env_prefix = "MCP_"


class RepositoryConfig(BaseSettings):
    """Repository configuration."""

    default_repo_url: str = "https://github.com/tiangolo/fastapi"
    """Default repository to index"""

    clone_path: str = "/tmp/repositories"
    """Path to clone repositories"""

    max_file_size_mb: int = 10
    """Maximum file size to process in MB"""

    class Config:
        """Pydantic config."""

        env_prefix = "REPO_"


class LoggingConfig(BaseSettings):
    """Logging configuration."""

    level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    """Logging level"""

    format: str = "json"
    """Log format: 'json' or 'text'"""

    class Config:
        """Pydantic config."""

        env_prefix = "LOG_"


class Config(BaseSettings):
    """
    Main configuration class - aggregates all sub-configs.

    WHAT: Root configuration for entire system
    WHY: Centralized settings management with type safety
    HOW: Pydantic Settings loads from environment variables

    Example:
        config = Config()
        
        # Access sub-configurations
        neo4j_uri = config.neo4j.uri
        openai_key = config.openai.api_key
        
        # Access direct settings
        env_mode = config.environment
    """
    # Environment mode
    environment: Literal["development", "testing", "production"] = "development"
    """Application environment"""

    # Sub-configurations
    neo4j: Neo4jConfig = Neo4jConfig()
    """Neo4j database settings"""

    openai: OpenAIConfig = OpenAIConfig()
    """OpenAI API settings"""

    mcp: MCPServerConfig = MCPServerConfig()
    """MCP server settings"""

    repository: RepositoryConfig = RepositoryConfig()
    """Repository indexing settings"""

    logging: LoggingConfig = LoggingConfig()
    """Logging settings"""

    # Gateway specific
    gateway_host: str = "0.0.0.0"
    """FastAPI gateway host"""

    gateway_port: int = 8000
    """FastAPI gateway port"""

    gateway_reload: bool = True
    """Enable auto-reload in development"""

    # Conversation management
    conversation_memory_size: int = 50
    """Number of messages to keep in memory per session"""

    session_timeout_minutes: int = 30
    """Session timeout in minutes"""

    class Config:
        """Pydantic config."""

        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False

    def __init__(self, **data):
        """
        Initialize configuration.

        Loads from environment variables with fallback to defaults.
        """
        super().__init__(**data)


# Global config instance
config = Config()