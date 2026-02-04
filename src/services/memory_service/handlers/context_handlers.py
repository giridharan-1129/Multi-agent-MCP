"""Conversation context handlers for Memory Service."""

from uuid import UUID
from typing import Optional
from ....shared.mcp_server import ToolResult

from ....shared.logger import get_logger

logger = get_logger(__name__)


async def get_context_handler(
    postgres_client,
    session_id: str,
    last_n_turns: int = 5
) -> ToolResult:
    """Handle get_context tool - returns context for orchestrator."""
    try:
        session_uuid = UUID(session_id)
        history = await postgres_client.get_conversation_history(
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
        logger.error(f"Failed to get context: {e}")
        return ToolResult(success=False, error=str(e))
