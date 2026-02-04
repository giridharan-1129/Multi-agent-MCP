"""Conversation turn handlers for Memory Service."""

from uuid import UUID
from typing import Optional
from ....shared.mcp_server import ToolResult

from ....shared.logger import get_logger

logger = get_logger(__name__)


async def store_turn_handler(
    postgres_client,
    redis_client,
    session_id: str,
    turn_number: int,
    role: str,
    content: str
) -> ToolResult:
    """Handle store_turn tool."""
    try:
        session_uuid = UUID(session_id)
        turn = await postgres_client.store_turn(
            session_uuid,
            turn_number,
            role,
            content
        )
        
        # Also cache in Redis
        await redis_client.store_conversation_turn(
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
        logger.error(f"Failed to store turn: {e}")
        return ToolResult(success=False, error=str(e))


async def get_history_handler(
    postgres_client,
    session_id: str,
    limit: int = 20
) -> ToolResult:
    """Handle get_history tool."""
    try:
        session_uuid = UUID(session_id)
        history = await postgres_client.get_conversation_history(session_uuid, limit)
        
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
        logger.error(f"Failed to get history: {e}")
        return ToolResult(success=False, error=str(e))
