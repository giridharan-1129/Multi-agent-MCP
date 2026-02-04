"""
Gateway dependencies - MCP service clients.

WHAT: Centralized access to MCP service clients
WHY: Manage service communication and health checks
HOW: Export client getters initialized during startup
"""

from typing import Optional
import httpx


import os

# Global MCP service URLs (read from environment)
MEMORY_SERVICE_URL: str = os.getenv("MEMORY_SERVICE_URL", "http://localhost:8005")
GRAPH_QUERY_SERVICE_URL: str = os.getenv("GRAPH_QUERY_SERVICE_URL", "http://localhost:8003")
CODE_ANALYST_SERVICE_URL: str = os.getenv("CODE_ANALYST_SERVICE_URL", "http://localhost:8004")
INDEXER_SERVICE_URL: str = os.getenv("INDEXER_SERVICE_URL", "http://localhost:8002")
ORCHESTRATOR_SERVICE_URL: str = os.getenv("ORCHESTRATOR_SERVICE_URL", "http://localhost:8001")

# HTTP clients
memory_client: Optional[httpx.AsyncClient] = None
orchestrator_client: Optional[httpx.AsyncClient] = None
graph_query_client: Optional[httpx.AsyncClient] = None
code_analyst_client: Optional[httpx.AsyncClient] = None
indexer_client: Optional[httpx.AsyncClient] = None


async def init_clients(
    memory_url: str = MEMORY_SERVICE_URL,
    orchestrator_url: str = ORCHESTRATOR_SERVICE_URL,
    graph_query_url: str = GRAPH_QUERY_SERVICE_URL,
    code_analyst_url: str = CODE_ANALYST_SERVICE_URL,
    indexer_url: str = INDEXER_SERVICE_URL,
) -> None:
    """Initialize HTTP clients for MCP services."""
    global memory_client, orchestrator_client, graph_query_client, code_analyst_client, indexer_client
    
    memory_client = httpx.AsyncClient(base_url=memory_url, timeout=30.0)
    orchestrator_client = httpx.AsyncClient(base_url=orchestrator_url, timeout=30.0)
    graph_query_client = httpx.AsyncClient(base_url=graph_query_url, timeout=30.0)
    code_analyst_client = httpx.AsyncClient(base_url=code_analyst_url, timeout=30.0)
    indexer_client = httpx.AsyncClient(base_url=indexer_url, timeout=30.0)


async def shutdown_clients() -> None:
    """Close all HTTP clients."""
    global memory_client, orchestrator_client, graph_query_client, code_analyst_client, indexer_client
    
    if memory_client:
        await memory_client.aclose()
    if orchestrator_client:
        await orchestrator_client.aclose()
    if graph_query_client:
        await graph_query_client.aclose()
    if code_analyst_client:
        await code_analyst_client.aclose()
    if indexer_client:
        await indexer_client.aclose()
    
    memory_client = None
    orchestrator_client = None
    graph_query_client = None
    code_analyst_client = None
    indexer_client = None
