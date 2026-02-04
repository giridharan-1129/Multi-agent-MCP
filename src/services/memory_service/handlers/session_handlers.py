"""Session management handlers for Memory Service."""

from uuid import UUID
from typing import Optional
from ....shared.mcp_server import ToolResult

from ....shared.logger import get_logger

logger = get_logger(__name__)


async def create_session_handler(
    postgres_client,
    redis_client,
    user_id: str,
    session_name: Optional[str] = None
) -> ToolResult:
    """Handle create_session tool."""
    try:
        session = await postgres_client.create_session(user_id, session_name)
        
        # Cache in Redis
        await redis_client.store_session(
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
        logger.error(f"Failed to create session: {e}")
        return ToolResult(success=False, error=str(e))


async def get_session_handler(
    postgres_client,
    session_id: str
) -> ToolResult:
    """Handle get_session tool."""
    try:
        session_uuid = UUID(session_id)
        session = await postgres_client.get_session(session_uuid)
        
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
        logger.error(f"Failed to get session: {e}")
        return ToolResult(success=False, error=str(e))


async def close_session_handler(
    postgres_client,
    redis_client,
    session_id: str
) -> ToolResult:
    """Handle close_session tool."""
    try:
        session_uuid = UUID(session_id)
        await postgres_client.close_session(session_uuid)
        
        # Clear Redis cache
        await redis_client.clear_conversation(session_id)
        
        return ToolResult(
            success=True,
            data={"session_id": session_id, "status": "closed"}
        )
    except Exception as e:
        logger.error(f"Failed to close session: {e}")
        return ToolResult(success=False, error=str(e))
