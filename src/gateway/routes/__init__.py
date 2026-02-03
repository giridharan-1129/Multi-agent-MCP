"""
Gateway routes package.

WHAT: All API endpoint routes
WHY: Organized endpoint management
HOW: Each route module handles a specific domain
"""

from .health import router as health_router

__all__ = [
    "health_router",
]
