"""Memory Service - MCP Server for conversation memory management."""

import os
from typing import Any, Dict

from ...shared.mcp_server import BaseMCPServer, ToolResult
from ...shared.redis_client import RedisClientManager
from ...shared.postgres_client import PostgreSQLClientManager
from ...shared.logger import get_logger
from .handlers import (
    create_session_handler,
    get_session_handler,
    close_session_handler,
    store_turn_handler,
    get_history_handler,
    store_agent_response_handler,
    get_context_handler,
)

logger = get_logger(__name__)


class MemoryService(BaseMCPServer):
    """MCP Server for conversation memory operations."""
    
    def __init__(self):
        super().__init__(
            service_name="MemoryService",
            host=os.getenv("MEMORY_HOST", "0.0.0.0"),
            port=int(os.getenv("MEMORY_PORT", 8005))
        )
        self.redis_client: RedisClientManager = None
        self.postgres_client: PostgreSQLClientManager = None
    
    async def register_tools(self):
        """Register memory management tools."""
        
        self.register_tool(
            name="create_session",
            description="Create a new conversation session",
            input_schema={
                "type": "object",
                "properties": {
                    "user_id": {"type": "string", "description": "User identifier"},
                    "session_name": {"type": "string", "description": "Optional session name"}
                },
                "required": ["user_id"]
            },
            handler=self._create_session_wrapper
        )
        
        self.register_tool(
            name="get_session",
            description="Retrieve a conversation session",
            input_schema={
                "type": "object",
                "properties": {
                    "session_id": {"type": "string", "description": "Session UUID"}
                },
                "required": ["session_id"]
            },
            handler=self._get_session_wrapper
        )
        
        self.register_tool(
            name="store_turn",
            description="Store a user or assistant message turn",
            input_schema={
                "type": "object",
                "properties": {
                    "session_id": {"type": "string", "description": "Session UUID"},
                    "turn_number": {"type": "integer", "description": "Turn sequence number"},
                    "role": {"type": "string", "enum": ["user", "assistant"], "description": "Who sent the message"},
                    "content": {"type": "string", "description": "Message content"}
                },
                "required": ["session_id", "turn_number", "role", "content"]
            },
            handler=self._store_turn_wrapper
        )
        
        self.register_tool(
            name="get_history",
            description="Retrieve conversation history",
            input_schema={
                "type": "object",
                "properties": {
                    "session_id": {"type": "string", "description": "Session UUID"},
                    "limit": {"type": "integer", "description": "Number of turns to retrieve (default: 20)"}
                },
                "required": ["session_id"]
            },
            handler=self._get_history_wrapper
        )
        
        self.register_tool(
            name="store_agent_response",
            description="Log an agent's response to a turn",
            input_schema={
                "type": "object",
                "properties": {
                    "turn_id": {"type": "string", "description": "Turn UUID"},
                    "agent_name": {"type": "string", "description": "Name of the agent"},
                    "tools_used": {"type": "array", "items": {"type": "string"}, "description": "List of tools used"},
                    "result": {"type": "string", "description": "Agent response result"},
                    "duration_ms": {"type": "integer", "description": "Execution time in milliseconds"}
                },
                "required": ["turn_id", "agent_name", "result"]
            },
            handler=self._store_agent_response_wrapper
        )
        
        self.register_tool(
            name="get_context",
            description="Get recent conversation context for orchestrator",
            input_schema={
                "type": "object",
                "properties": {
                    "session_id": {"type": "string", "description": "Session UUID"},
                    "last_n_turns": {"type": "integer", "description": "Number of recent turns to include (default: 5)"}
                },
                "required": ["session_id"]
            },
            handler=self._get_context_wrapper
        )
        
        self.register_tool(
            name="close_session",
            description="Close a conversation session",
            input_schema={
                "type": "object",
                "properties": {
                    "session_id": {"type": "string", "description": "Session UUID"}
                },
                "required": ["session_id"]
            },
            handler=self._close_session_wrapper
        )
        
        self.logger.info("Registered 7 memory management tools")
    
    async def _setup_service(self):
        """Initialize Redis and PostgreSQL clients."""
        try:
            redis_url = os.getenv("REDIS_URL", "redis://:redis_password@localhost:6379/0")
            self.redis_client = RedisClientManager(redis_url)
            
            db_url = os.getenv("DATABASE_URL", "postgresql://postgres:postgres_password@localhost:5432/codebase_chat")
            if db_url.startswith("postgresql://"):
                db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)
            
            self.postgres_client = PostgreSQLClientManager(db_url)
            await self.postgres_client.initialize()
            
            self.logger.info("Memory service initialized successfully")
        except Exception as e:
            self.logger.error(f"Failed to initialize memory service: {e}")
            raise
    
    
    async def _create_session_wrapper(self, user_id: str, session_name: str = None) -> ToolResult:
        return await create_session_handler(self.postgres_client, self.redis_client, user_id, session_name)
    
    async def _get_session_wrapper(self, session_id: str) -> ToolResult:
        return await get_session_handler(self.postgres_client, session_id)
    
    async def _store_turn_wrapper(self, session_id: str, turn_number: int, role: str, content: str) -> ToolResult:
        return await store_turn_handler(self.postgres_client, self.redis_client, session_id, turn_number, role, content)
    
    async def _get_history_wrapper(self, session_id: str, limit: int = 20) -> ToolResult:
        return await get_history_handler(self.postgres_client, session_id, limit)
    
    async def _store_agent_response_wrapper(self, turn_id: str, agent_name: str, result: str, tools_used: list = None, duration_ms: int = None) -> ToolResult:
        return await store_agent_response_handler(self.postgres_client, turn_id, agent_name, result, tools_used, duration_ms)
    
    async def _get_context_wrapper(self, session_id: str, last_n_turns: int = 5) -> ToolResult:
        return await get_context_handler(self.postgres_client, session_id, last_n_turns)
    
    async def _close_session_wrapper(self, session_id: str) -> ToolResult:
        return await close_session_handler(self.postgres_client, self.redis_client, session_id)
    
    async def _cleanup_service(self):
        """Cleanup database and Redis connections."""
        if self.postgres_client:
            await self.postgres_client.close()
        if self.redis_client:
            self.redis_client.close()
