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
        # Intent-to-agents mapping
        ROUTING_MAP = {
            # ===== GRAPH QUERY AGENT (Parallel Neo4j + Pinecone) =====
            "search": ["graph_query"],        # Find entities quickly
            
            # ===== CODE ANALYST AGENT (Deep code understanding) =====
            "explain": ["graph_query", "code_analyst"],      # Entity info + deep explanation
            "analyze": ["code_analyst"],                       # Detailed code analysis
            "compare": ["code_analyst"],                       # Side-by-side comparison
            "pattern": ["code_analyst"],                       # Design pattern detection
            
            # ===== INDEXER AGENT (Repository management) =====
            "index": ["indexer"],              # Full repo indexing
            "embed": ["indexer"],              # Semantic indexing to Pinecone
            "stats": ["indexer"],              # Repository statistics
            
            # ===== FALLBACK =====
            "default": ["graph_query"]         # Default to search
        }

        agents = ROUTING_MAP.get(intent, ROUTING_MAP["default"])
        parallel = len(agents) > 1  # Keep as is
        logger.info(f"🛣️  ROUTING: intent='{intent}' → agents={agents}")
        logger.info(f"   Reason: {intent} intent routed to {agents}")
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
