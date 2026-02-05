"""Handler for context retrieval."""

from typing import Optional
from uuid import UUID

from ....shared.mcp_server import ToolResult
from ....shared.postgres_client import PostgreSQLClientManager
from ....shared.logger import get_logger

logger = get_logger(__name__)


async def get_context_handler(
    postgres_client: PostgreSQLClientManager,
    session_id: str,
    last_n_turns: int = 5
) -> ToolResult:
    """Get recent conversation context for orchestrator."""
    try:
        logger.info(f"📖 get_context_handler: session_id={session_id}, last_n={last_n_turns}")
        
        # Handle new sessions gracefully
        if session_id == "new" or not session_id:
            logger.info("   ℹ️ New session detected - returning empty context")
            return ToolResult(
                success=True,
                data={
                    "session_id": "new",
                    "context_turns": [],
                    "context_length": 0,
                    "is_new_session": True
                }
            )
        
        # Validate UUID format
        try:
            session_uuid = UUID(session_id)
        except ValueError:
            logger.warning(f"   ⚠️ Invalid UUID format: {session_id}")
            return ToolResult(
                success=True,
                data={
                    "session_id": session_id,
                    "context_turns": [],
                    "context_length": 0,
                    "is_new_session": True
                }
            )
        
        # Get history from PostgreSQL
        history = await postgres_client.get_conversation_history(session_uuid, limit=last_n_turns)
        logger.info(f"   ✅ Retrieved {len(history)} turns from history")
        
        # Format as context turns
        # Format as context turns
        context_turns = [
            {
                "role": turn.role if hasattr(turn, 'role') else "user",
                "content": turn.content if hasattr(turn, 'content') else ""
            }
            for turn in history
        ]
        
        return ToolResult(
            success=True,
            data={
                "session_id": str(session_uuid),
                "context_turns": context_turns,
                "context_length": len(context_turns),
                "is_new_session": False
            }
        )
        
    except Exception as e:
        logger.error(f"❌ Failed to get context: {e}")
        import traceback
        logger.error(traceback.format_exc())
        # Don't fail - just return empty context
        return ToolResult(
            success=True,
            data={
                "session_id": session_id,
                "context_turns": [],
                "context_length": 0,
                "error": str(e)
            }
        )