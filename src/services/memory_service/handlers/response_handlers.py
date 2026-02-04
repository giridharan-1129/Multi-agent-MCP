"""Agent response handlers for Memory Service."""

from uuid import UUID
from typing import Optional, List
from ....shared.mcp_server import ToolResult

from ....shared.logger import get_logger

logger = get_logger(__name__)


async def store_agent_response_handler(
    postgres_client,
    turn_id: str,
    agent_name: str,
    result: str,
    tools_used: Optional[List[str]] = None,
    duration_ms: Optional[int] = None
) -> ToolResult:
    """Handle store_agent_response tool."""
    try:
        turn_uuid = UUID(turn_id)
        response = await postgres_client.store_agent_response(
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
        logger.error(f"Failed to store agent response: {e}")
        return ToolResult(success=False, error=str(e))
