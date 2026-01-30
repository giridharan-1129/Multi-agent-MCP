"""
Gateway dependencies and globals.

WHAT: Centralized access to global agent instances
WHY: Avoid circular imports and manage agent lifecycle
HOW: Export agent getters that are initialized during startup
"""

from typing import Optional

from ..agents.orchestrator_agent import OrchestratorAgent
from ..agents.indexer_agent import IndexerAgent
from ..agents.graph_query_agent import GraphQueryAgent
from ..agents.code_analyst_agent import CodeAnalystAgent

# Global agent instances (initialized during app startup)
orchestrator: Optional[OrchestratorAgent] = None
indexer: Optional[IndexerAgent] = None
graph_query: Optional[GraphQueryAgent] = None
code_analyst: Optional[CodeAnalystAgent] = None


def get_orchestrator() -> OrchestratorAgent:
    """Get orchestrator agent instance."""
    global orchestrator
    if not orchestrator:
        raise RuntimeError("Orchestrator not initialized")
    return orchestrator


def get_indexer() -> IndexerAgent:
    """Get indexer agent instance."""
    global indexer
    if not indexer:
        raise RuntimeError("Indexer not initialized")
    return indexer


def get_graph_query() -> GraphQueryAgent:
    """Get graph query agent instance."""
    global graph_query
    if not graph_query:
        raise RuntimeError("Graph query agent not initialized")
    return graph_query


def get_code_analyst() -> CodeAnalystAgent:
    """Get code analyst agent instance."""
    global code_analyst
    if not code_analyst:
        raise RuntimeError("Code analyst not initialized")
    return code_analyst


def init_agents(orch, idx, gq, ca) -> None:
    """
    Initialize global agent instances.
    
    Args:
        orch: Orchestrator agent
        idx: Indexer agent
        gq: Graph query agent
        ca: Code analyst agent
    """
    global orchestrator, indexer, graph_query, code_analyst
    orchestrator = orch
    indexer = idx
    graph_query = gq
    code_analyst = ca


def shutdown_agents() -> None:
    """Reset global agent instances (for shutdown)."""
    global orchestrator, indexer, graph_query, code_analyst
    orchestrator = None
    indexer = None
    graph_query = None
    code_analyst = None
