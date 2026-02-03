"""
MCP Client Helper - Utilities for communicating with MCP services.

Provides methods to call remote MCP services from the gateway.
"""

import httpx
from typing import Any, Dict, Optional
import logging

from ..shared.logger import get_logger

logger = get_logger(__name__)


class MCPClient:
    """Client for communicating with MCP services."""
    
    def __init__(self, service_url: str, timeout: float = 30.0):
        """
        Initialize MCP client.
        
        Args:
            service_url: Base URL of the MCP service
            timeout: Request timeout in seconds
        """
        self.service_url = service_url
        self.timeout = timeout
    
    async def get_tools(self) -> Optional[Dict[str, Any]]:
        """Get available tools from the service."""
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(f"{self.service_url}/tools")
                if resp.status_code == 200:
                    return resp.json()
                else:
                    logger.error(f"Failed to get tools: {resp.status_code}")
                    return None
        except Exception as e:
            logger.error(f"MCP client error getting tools: {e}")
            return None
    
    async def execute_tool(
        self,
        tool_name: str,
        tool_input: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """
        Execute a tool on the service.
        
        Args:
            tool_name: Name of the tool to execute
            tool_input: Input parameters for the tool
        
        Returns:
            Tool result or None if failed
        """
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(
                    f"{self.service_url}/execute?tool_name={tool_name}",
                    json=tool_input
                )
                if resp.status_code == 200:
                    return resp.json()
                else:
                    logger.error(f"Tool execution failed: {resp.status_code}")
                    return None
        except Exception as e:
            logger.error(f"MCP client error executing tool: {e}")
            return None
    
    async def health_check(self) -> bool:
        """Check if service is healthy."""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{self.service_url}/health")
                return resp.status_code == 200
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return False


class OrchestratorClient(MCPClient):
    """Specialized client for Orchestrator Service."""
    
    async def analyze_query(self, query: str) -> Optional[Dict[str, Any]]:
        """Analyze a query."""
        return await self.execute_tool("analyze_query", {"query": query})
    
    async def route_to_agents(
        self,
        query: str,
        intent: str
    ) -> Optional[Dict[str, Any]]:
        """Route query to appropriate agents."""
        return await self.execute_tool(
            "route_to_agents",
            {"query": query, "intent": intent}
        )
    
    async def get_conversation_context(
        self,
        session_id: str,
        limit: int = 5
    ) -> Optional[Dict[str, Any]]:
        """Get conversation context."""
        return await self.execute_tool(
            "get_conversation_context",
            {"session_id": session_id, "limit": limit}
        )
    
    async def call_agent_tool(
        self,
        agent: str,
        tool: str,
        input_params: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Call a tool on a specific agent."""
        return await self.execute_tool(
            "call_agent_tool",
            {"agent": agent, "tool": tool, "input": input_params}
        )
    
    async def synthesize_response(
        self,
        agent_results: list,
        original_query: str
    ) -> Optional[Dict[str, Any]]:
        """Synthesize agent results into response."""
        return await self.execute_tool(
            "synthesize_response",
            {"agent_results": agent_results, "original_query": original_query}
        )
    
    async def store_agent_response(
        self,
        turn_id: str,
        agent_name: str,
        result: str,
        tools_used: list = None
    ) -> Optional[Dict[str, Any]]:
        """Store agent response in memory."""
        return await self.execute_tool(
            "store_agent_response",
            {
                "turn_id": turn_id,
                "agent_name": agent_name,
                "result": result,
                "tools_used": tools_used or []
            }
        )


class MemoryClient(MCPClient):
    """Specialized client for Memory Service."""
    
    async def create_session(
        self,
        user_id: str,
        session_name: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Create a new conversation session."""
        return await self.execute_tool(
            "create_session",
            {"user_id": user_id, "session_name": session_name}
        )
    
    async def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get session details."""
        return await self.execute_tool(
            "get_session",
            {"session_id": session_id}
        )
    
    async def store_turn(
        self,
        session_id: str,
        turn_number: int,
        role: str,
        content: str
    ) -> Optional[Dict[str, Any]]:
        """Store a conversation turn."""
        return await self.execute_tool(
            "store_turn",
            {
                "session_id": session_id,
                "turn_number": turn_number,
                "role": role,
                "content": content
            }
        )
    
    async def get_history(
        self,
        session_id: str,
        limit: int = 20
    ) -> Optional[Dict[str, Any]]:
        """Get conversation history."""
        return await self.execute_tool(
            "get_history",
            {"session_id": session_id, "limit": limit}
        )
    
    async def close_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Close a conversation session."""
        return await self.execute_tool(
            "close_session",
            {"session_id": session_id}
        )


class GraphQueryClient(MCPClient):
    """Specialized client for Graph Query Service."""
    
    async def find_entity(
        self,
        name: str,
        entity_type: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Find an entity in the knowledge graph."""
        return await self.execute_tool(
            "find_entity",
            {"name": name, "entity_type": entity_type}
        )
    
    async def get_dependencies(self, name: str) -> Optional[Dict[str, Any]]:
        """Get dependencies of an entity."""
        return await self.execute_tool(
            "get_dependencies",
            {"name": name}
        )
    
    async def get_dependents(self, name: str) -> Optional[Dict[str, Any]]:
        """Get entities that depend on an entity."""
        return await self.execute_tool(
            "get_dependents",
            {"name": name}
        )
    
    async def execute_query(
        self,
        query: str,
        parameters: Optional[Dict[str, Any]] = None
    ) -> Optional[Dict[str, Any]]:
        """Execute a custom Cypher query."""
        return await self.execute_tool(
            "execute_query",
            {"query": query, "parameters": parameters or {}}
        )


class CodeAnalystClient(MCPClient):
    """Specialized client for Code Analyst Service."""
    
    async def analyze_function(self, name: str) -> Optional[Dict[str, Any]]:
        """Analyze a function."""
        return await self.execute_tool(
            "analyze_function",
            {"name": name}
        )
    
    async def analyze_class(self, name: str) -> Optional[Dict[str, Any]]:
        """Analyze a class."""
        return await self.execute_tool(
            "analyze_class",
            {"name": name}
        )
    
    async def find_patterns(
        self,
        pattern_type: Optional[str] = None
    ) -> Optional[Dict[str, Any]]:
        """Find design patterns."""
        return await self.execute_tool(
            "find_patterns",
            {"pattern_type": pattern_type}
        )
    
    async def compare_implementations(
        self,
        entity1: str,
        entity2: str
    ) -> Optional[Dict[str, Any]]:
        """Compare two implementations."""
        return await self.execute_tool(
            "compare_implementations",
            {"entity1": entity1, "entity2": entity2}
        )


class IndexerClient(MCPClient):
    """Specialized client for Indexer Service."""
    
    async def index_repository(
        self,
        repo_url: str,
        branch: str = "main"
    ) -> Optional[Dict[str, Any]]:
        """Index a repository."""
        return await self.execute_tool(
            "index_repository",
            {"repo_url": repo_url, "branch": branch}
        )
    
    async def get_index_status(self) -> Optional[Dict[str, Any]]:
        """Get indexing status."""
        return await self.execute_tool(
            "get_index_status",
            {}
        )
    
    async def clear_index(self) -> Optional[Dict[str, Any]]:
        """Clear all indexed data."""
        return await self.execute_tool(
            "clear_index",
            {}
        )
