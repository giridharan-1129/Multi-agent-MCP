"""
Gateway routes package.

WHAT: All API endpoint routes
WHY: Organized endpoint management
HOW: Each route module handles a specific domain
"""

from .health import router as health_router
from .chat import router as chat_router
from .websocket import router as websocket_router
from .indexing import router as indexing_router
from .query import router as query_router
from .analysis import router as analysis_router
from .rag_chat import router as rag_chat_router
from .graph_visualization import router as graph_visualization_router
from .embeddings import router as embeddings_router
from .agentic_chat import router as agentic_router
__all__ = [
    "health_router",
    "chat_router",
    "websocket_router",
    "indexing_router",
    "query_router",
    "analysis_router",
    "rag_chat_router",
    "graph_visualization_router",
    "embeddings_router",
    "agentic_router",

]
