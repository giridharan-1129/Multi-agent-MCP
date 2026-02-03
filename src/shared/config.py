"""
Shared Configuration Module.

WHAT: Central configuration for all agents and gateway
WHY: Single source of truth for settings, secrets, and credentials
HOW: Pydantic Settings loads from environment variables with type safety
"""

from typing import Literal, Optional
from pydantic_settings import BaseSettings


class Neo4jConfig(BaseSettings):
    """Neo4j database configuration."""
    uri: str = "bolt://localhost:7687"
    username: str = "neo4j"
    password: str = "password"
    database: str = "neo4j"

    class Config:
        env_prefix = "NEO4J_"
        extra = "ignore"


class PostgresConfig(BaseSettings):
    """PostgreSQL database configuration."""
    database_url: str = "postgresql://postgres:postgres_password@localhost:5432/codebase_chat"

    class Config:
        extra = "ignore"


class RedisConfig(BaseSettings):
    """Redis configuration."""
    redis_url: str = "redis://:redis_password@localhost:6379/0"

    class Config:
        extra = "ignore"


class OpenAIConfig(BaseSettings):
    """OpenAI configuration."""
    api_key: Optional[str] = None
    model: str = "gpt-4"
    temperature: float = 0.7
    max_tokens: int = 2000

    class Config:
        env_prefix = "OPENAI_"
        extra = "ignore"


class PineconeConfig(BaseSettings):
    """Pinecone configuration."""
    api_key: Optional[str] = None
    index_name: Optional[str] = None

    class Config:
        env_prefix = "PINECONE_"
        extra = "ignore"


class CohereConfig(BaseSettings):
    """Cohere configuration."""
    api_key: Optional[str] = None

    class Config:
        env_prefix = "COHERE_"
        extra = "ignore"


class MCPServerConfig(BaseSettings):
    """MCP Server configuration."""
    host: str = "localhost"
    port: int = 8000
    timeout: int = 30
    retry_attempts: int = 3

    class Config:
        env_prefix = "MCP_"
        extra = "ignore"


class RepositoryConfig(BaseSettings):
    """Repository configuration."""
    default_repo_url: str = "https://github.com/tiangolo/fastapi"
    clone_path: str = "/tmp/repositories"
    max_file_size_mb: int = 10

    class Config:
        env_prefix = "REPO_"
        extra = "ignore"


class LoggingConfig(BaseSettings):
    """Logging configuration."""
    level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    format: str = "json"

    class Config:
        env_prefix = "LOG_"
        extra = "ignore"


class Config(BaseSettings):
    """Main configuration class."""
    
    environment: Literal["development", "testing", "production"] = "development"
    
    # Sub-configurations
    neo4j: Neo4jConfig = Neo4jConfig()
    postgres: PostgresConfig = PostgresConfig()
    redis: RedisConfig = RedisConfig()
    openai: OpenAIConfig = OpenAIConfig()
    pinecone: PineconeConfig = PineconeConfig()
    cohere: CohereConfig = CohereConfig()
    mcp: MCPServerConfig = MCPServerConfig()
    repository: RepositoryConfig = RepositoryConfig()
    logging: LoggingConfig = LoggingConfig()
    
    # Gateway specific
    gateway_host: str = "0.0.0.0"
    gateway_port: int = 8000
    gateway_reload: bool = True
    
    # Service URLs
    memory_service_url: str = "http://localhost:8005"
    graph_query_service_url: str = "http://localhost:8003"
    code_analyst_service_url: str = "http://localhost:8004"
    indexer_service_url: str = "http://localhost:8002"
    orchestrator_service_url: str = "http://localhost:8001"
    
    # Conversation management
    conversation_memory_size: int = 50
    session_timeout_minutes: int = 30
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False
        extra = "ignore"


# Global config instance
config = Config()
