"""
FastAPI Multi-Agent Chat System.

A multi-agent system for analyzing GitHub repositories using the Model Context Protocol (MCP).

Agents:
- Orchestrator: Routes queries to appropriate agents
- Indexer: Indexes repositories into knowledge graph
- GraphQuery: Queries the knowledge graph
- CodeAnalyst: Analyzes code patterns and provides insights

Entry point: src.gateway.main:app
"""

__version__ = "1.0.0"
__author__ = "AI Engineer"

from .shared import config, get_logger

logger = get_logger(__name__)

__all__ = ["config", "get_logger", "logger"]

