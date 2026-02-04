"""Routing handler - determines which agents should handle the query."""

from typing import Dict, List
from ....shared.mcp_server import ToolResult

from ....shared.logger import get_logger

logger = get_logger(__name__)


async def route_to_agents(
    query: str,
    intent: str
) -> ToolResult:
    """
    Route query to appropriate agents based on intent.
    
    Args:
        query: User query
        intent: Classified intent from query analysis
        
    Returns:
        ToolResult with recommended_agents list and parallel flag
    """
    try:
        # Intent-to-agents mapping
        ROUTING_MAP = {
            "search": ["graph_query"],
            "explain": ["graph_query", "code_analyst"],
            "analyze": ["code_analyst", "graph_query"],
            "list": ["graph_query"],
            "implement": ["indexer"],
            "index": ["indexer"],
            "embed": ["indexer"],
            "stats": ["indexer"],
            "status": ["indexer"],
            "query": ["indexer"]
        }
        
        agents = ROUTING_MAP.get(intent, ["graph_query"])
        parallel = len(agents) > 1
        
        logger.debug(f"🛣️  Routing: intent={intent} → agents={agents}, parallel={parallel}")
        
        return ToolResult(
            success=True,
            data={
                "query": query,
                "intent": intent,
                "recommended_agents": agents,
                "parallel": parallel
            }
        )
    except Exception as e:
        logger.error(f"Failed to route to agents: {e}")
        return ToolResult(success=False, error=str(e))
