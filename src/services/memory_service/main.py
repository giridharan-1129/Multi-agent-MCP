"""
Memory Service - MCP Server for conversation memory management.

Responsibilities:
- Store and retrieve conversation sessions
- Manage conversation turns
- Log agent responses
- Provide conversation context
- Cache recent conversations in Redis
"""

import asyncio
import os
from typing import Any, Dict
import logging

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from ...shared.mcp_server import BaseMCPServer, ToolResult
from ...shared.redis_client import RedisClientManager
from ...shared.postgres_client import PostgreSQLClientManager
from ...shared.conversation_models import (
    ConversationSession,
    ConversationTurn,
    AgentResponse,
    MemoryQuery,
    MemoryStore,
    AgentResponseStore,
)
from ...shared.logger import get_logger
from uuid import UUID

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
        
        # Tool 1: Create Session
        self.register_tool(
            name="create_session",
            description="Create a new conversation session",
            input_schema={
                "type": "object",
                "properties": {
                    "user_id": {
                        "type": "string",
                        "description": "User identifier"
                    },
                    "session_name": {
                        "type": "string",
                        "description": "Optional session name"
                    }
                },
                "required": ["user_id"]
            },
            handler=self.create_session_handler
        )
        
        # Tool 2: Get Session
        self.register_tool(
            name="get_session",
            description="Retrieve a conversation session",
            input_schema={
                "type": "object",
                "properties": {
                    "session_id": {
                        "type": "string",
                        "description": "Session UUID"
                    }
                },
                "required": ["session_id"]
            },
            handler=self.get_session_handler
        )
        
        # Tool 3: Store Conversation Turn
        self.register_tool(
            name="store_turn",
            description="Store a user or assistant message turn",
            input_schema={
                "type": "object",
                "properties": {
                    "session_id": {
                        "type": "string",
                        "description": "Session UUID"
                    },
                    "turn_number": {
                        "type": "integer",
                        "description": "Turn sequence number"
                    },
                    "role": {
                        "type": "string",
                        "enum": ["user", "assistant"],
                        "description": "Who sent the message"
                    },
                    "content": {
                        "type": "string",
                        "description": "Message content"
                    }
                },
                "required": ["session_id", "turn_number", "role", "content"]
            },
            handler=self.store_turn_handler
        )
        
        # Tool 4: Get Conversation History
        self.register_tool(
            name="get_history",
            description="Retrieve conversation history",
            input_schema={
                "type": "object",
                "properties": {
                    "session_id": {
                        "type": "string",
                        "description": "Session UUID"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Number of turns to retrieve (default: 20)"
                    }
                },
                "required": ["session_id"]
            },
            handler=self.get_history_handler
        )
        
        # Tool 5: Store Agent Response
        self.register_tool(
            name="store_agent_response",
            description="Log an agent's response to a turn",
            input_schema={
                "type": "object",
                "properties": {
                    "turn_id": {
                        "type": "string",
                        "description": "Turn UUID"
                    },
                    "agent_name": {
                        "type": "string",
                        "description": "Name of the agent"
                    },
                    "tools_used": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of tools used"
                    },
                    "result": {
                        "type": "string",
                        "description": "Agent response result"
                    },
                    "duration_ms": {
                        "type": "integer",
                        "description": "Execution time in milliseconds"
                    }
                },
                "required": ["turn_id", "agent_name", "result"]
            },
            handler=self.store_agent_response_handler
        )
        
        # Tool 6: Get Conversation Context
        self.register_tool(
            name="get_context",
            description="Get recent conversation context for orchestrator",
            input_schema={
                "type": "object",
                "properties": {
                    "session_id": {
                        "type": "string",
                        "description": "Session UUID"
                    },
                    "last_n_turns": {
                        "type": "integer",
                        "description": "Number of recent turns to include (default: 5)"
                    }
                },
                "required": ["session_id"]
            },
            handler=self.get_context_handler
        )
        
        # Tool 7: Close Session
        self.register_tool(
            name="close_session",
            description="Close a conversation session",
            input_schema={
                "type": "object",
                "properties": {
                    "session_id": {
                        "type": "string",
                        "description": "Session UUID"
                    }
                },
                "required": ["session_id"]
            },
            handler=self.close_session_handler
        )
        
        self.logger.info("Registered 7 memory management tools")
    
    async def _setup_service(self):
        """Initialize Redis and PostgreSQL clients."""
        try:
            redis_url = os.getenv("REDIS_URL", "redis://:redis_password@localhost:6379/0")
            self.redis_client = RedisClientManager(redis_url)
            
            db_url = os.getenv("DATABASE_URL", "postgresql://postgres:postgres_password@localhost:5432/codebase_chat")
            # Convert to async URL if needed
            if db_url.startswith("postgresql://"):
                db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)
            
            self.postgres_client = PostgreSQLClientManager(db_url)
            await self.postgres_client.initialize()
            
            self.logger.info("Memory service initialized successfully")
        except Exception as e:
            self.logger.error(f"Failed to initialize memory service: {e}")
            raise
    
    # ============================================================================
    # TOOL HANDLERS
    # ============================================================================
    
    async def create_session_handler(
        self,
        user_id: str,
        session_name: str = None
    ) -> ToolResult:
        """Handle create_session tool."""
        try:
            session = await self.postgres_client.create_session(user_id, session_name)
            
            # Cache in Redis
            await self.redis_client.store_session(
                str(session.id),
                {
                    "id": str(session.id),
                    "user_id": session.user_id,
                    "session_name": session.session_name,
                    "created_at": session.created_at.isoformat() if session.created_at else None
                }
            )
            
            return ToolResult(
                success=True,
                data={
                    "session_id": str(session.id),
                    "user_id": session.user_id,
                    "created_at": session.created_at.isoformat() if session.created_at else None
                }
            )
        except Exception as e:
            self.logger.error(f"Failed to create session: {e}")
            return ToolResult(success=False, error=str(e))
    
    async def get_session_handler(self, session_id: str) -> ToolResult:
        """Handle get_session tool."""
        try:
            session_uuid = UUID(session_id)
            session = await self.postgres_client.get_session(session_uuid)
            
            if not session:
                return ToolResult(success=False, error=f"Session not found: {session_id}")
            
            return ToolResult(
                success=True,
                data={
                    "id": str(session.id),
                    "user_id": session.user_id,
                    "session_name": session.session_name,
                    "created_at": session.created_at.isoformat() if session.created_at else None
                }
            )
        except Exception as e:
            self.logger.error(f"Failed to get session: {e}")
            return ToolResult(success=False, error=str(e))
    
    async def store_turn_handler(
        self,
        session_id: str,
        turn_number: int,
        role: str,
        content: str
    ) -> ToolResult:
        """Handle store_turn tool."""
        try:
            session_uuid = UUID(session_id)
            turn = await self.postgres_client.store_turn(
                session_uuid,
                turn_number,
                role,
                content
            )
            
            # Also cache in Redis
            await self.redis_client.store_conversation_turn(
                session_id,
                turn_number,
                role,
                content
            )
            
            return ToolResult(
                success=True,
                data={
                    "turn_id": str(turn.id),
                    "turn_number": turn.turn_number,
                    "role": turn.role
                }
            )
        except Exception as e:
            self.logger.error(f"Failed to store turn: {e}")
            return ToolResult(success=False, error=str(e))
    
    async def get_history_handler(
        self,
        session_id: str,
        limit: int = 20
    ) -> ToolResult:
        """Handle get_history tool."""
        try:
            session_uuid = UUID(session_id)
            history = await self.postgres_client.get_conversation_history(session_uuid, limit)
            
            return ToolResult(
                success=True,
                data={
                    "session_id": session_id,
                    "turns": [
                        {
                            "turn_number": turn.turn_number,
                            "role": turn.role,
                            "content": turn.content,
                            "created_at": turn.created_at.isoformat() if turn.created_at else None
                        }
                        for turn in history
                    ]
                }
            )
        except Exception as e:
            self.logger.error(f"Failed to get history: {e}")
            return ToolResult(success=False, error=str(e))
    
    async def store_agent_response_handler(
        self,
        turn_id: str,
        agent_name: str,
        result: str,
        tools_used: list = None,
        duration_ms: int = None
    ) -> ToolResult:
        """Handle store_agent_response tool."""
        try:
            turn_uuid = UUID(turn_id)
            response = await self.postgres_client.store_agent_response(
                turn_uuid,
                agent_name,
                tools_used or [],
                result,
                duration_ms
            )
            
            return ToolResult(
                success=True,
                data={
                    "response_id": str(response.id),
                    "agent_name": response.agent_name,
                    "duration_ms": response.duration_ms
                }
            )
        except Exception as e:
            self.logger.error(f"Failed to store agent response: {e}")
            return ToolResult(success=False, error=str(e))
    
    async def get_context_handler(
        self,
        session_id: str,
        last_n_turns: int = 5
    ) -> ToolResult:
        """Handle get_context tool - returns context for orchestrator."""
        try:
            session_uuid = UUID(session_id)
            history = await self.postgres_client.get_conversation_history(
                session_uuid,
                limit=last_n_turns
            )
            
            return ToolResult(
                success=True,
                data={
                    "session_id": session_id,
                    "context_turns": [
                        {
                            "turn_number": turn.turn_number,
                            "role": turn.role,
                            "content": turn.content[:500]  # Truncate for context
                        }
                        for turn in history
                    ]
                }
            )
        except Exception as e:
            self.logger.error(f"Failed to get context: {e}")
            return ToolResult(success=False, error=str(e))
    
    async def close_session_handler(self, session_id: str) -> ToolResult:
        """Handle close_session tool."""
        try:
            session_uuid = UUID(session_id)
            await self.postgres_client.close_session(session_uuid)
            
            # Clear Redis cache
            await self.redis_client.clear_conversation(session_id)
            
            return ToolResult(
                success=True,
                data={"session_id": session_id, "status": "closed"}
            )
        except Exception as e:
            self.logger.error(f"Failed to close session: {e}")
            return ToolResult(success=False, error=str(e))
    
    async def _cleanup_service(self):
        """Cleanup database and Redis connections."""
        if self.postgres_client:
            await self.postgres_client.close()
        if self.redis_client:
            self.redis_client.close()


# ============================================================================
# FASTAPI APP FOR HTTP ENDPOINTS
# ============================================================================

app = FastAPI(title="Memory Service", version="1.0.0")
memory_service: MemoryService = None


@app.on_event("startup")
async def startup():
    """Initialize memory service on startup."""
    global memory_service
    memory_service = MemoryService()
    await memory_service.initialize()


@app.on_event("shutdown")
async def shutdown():
    """Cleanup on shutdown."""
    if memory_service:
        await memory_service.shutdown()


@app.get("/health")
async def health():
    """Health check endpoint."""
    if not memory_service:
        raise HTTPException(status_code=503, detail="Service not initialized")
    
    pg_healthy = await memory_service.postgres_client.health_check()
    redis_healthy = await memory_service.redis_client.health_check()
    
    if not (pg_healthy and redis_healthy):
        raise HTTPException(status_code=503, detail="Database connection failed")
    
    return {
        "status": "healthy",
        "service": "MemoryService",
        "postgres": "ok" if pg_healthy else "error",
        "redis": "ok" if redis_healthy else "error",
        "tools": len(memory_service.tools)
    }


@app.get("/tools")
async def get_tools():
    """Get available tools schema."""
    if not memory_service:
        raise HTTPException(status_code=503, detail="Service not initialized")
    
    return {
        "service": "MemoryService",
        "tools": memory_service.get_tools_schema()
    }


@app.post("/execute")
async def execute_tool(tool_name: str, tool_input: Dict[str, Any]):
    """Execute a tool."""
    if not memory_service:
        raise HTTPException(status_code=503, detail="Service not initialized")
    
    result = await memory_service.execute_tool(tool_name, tool_input)
    return result.dict()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app,
        host=os.getenv("MEMORY_HOST", "0.0.0.0"),
        port=int(os.getenv("MEMORY_PORT", 8005))
    )
