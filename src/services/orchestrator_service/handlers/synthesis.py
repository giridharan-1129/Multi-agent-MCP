"""Synthesis handler - combines multiple agent outputs into coherent response."""

from typing import Any, Dict, List

from ....shared.mcp_server import ToolResult

from ....shared.logger import get_logger

logger = get_logger(__name__)


async def synthesize_response(
    agent_results: List[Dict[str, Any]],
    original_query: str
) -> ToolResult:
    """
    Combine agent outputs into a coherent response.
    
    Args:
        agent_results: List of results from agents
        original_query: Original user query
        
    Returns:
        ToolResult with synthesized response and agents_used list
    """
    try:
        if not agent_results:
            return ToolResult(
                success=True,
                data={
                    "response": f"Query: {original_query}\n\nNo agent results available.",
                    "agents_used": []
                }
            )
        
        # Build comprehensive synthesis
        lines = [f"**Query:** {original_query}\n"]
        agents_used = []
        
        for idx, result in enumerate(agent_results, 1):
            agent_name = result.get("agent", result.get("agent_name", "Unknown"))
            data = result.get("data", {})
            agents_used.append(agent_name)
            
            lines.append(f"\n**[{idx}] {agent_name}:**")
            
            # Handle different data formats
            if isinstance(data, dict):
                if data.get("error"):
                    lines.append(f"Error: {data.get('error')}")
                else:
                    for key, value in data.items():
                        if value is not None:
                            if isinstance(value, list) and len(value) > 0:
                                lines.append(f"  • {key}: {', '.join(map(str, value[:5]))}")
                            elif isinstance(value, dict):
                                lines.append(f"  • {key}: {len(value)} items")
                            else:
                                lines.append(f"  • {key}: {str(value)[:200]}")
            else:
                lines.append(f"  {str(data)[:300]}")
        
        logger.debug(f"🔗 Response synthesized from {len(agents_used)} agents")
        
        return ToolResult(
            success=True,
            data={
                "response": "\n".join(lines),
                "agents_used": list(set(agents_used)),
                "num_agents": len(agent_results)
            }
        )
    except Exception as e:
        logger.error(f"Failed to synthesize response: {e}")
        return ToolResult(success=False, error=str(e))
