"""OrchestratorService - Main service class."""

"""OrchestratorService - Main service class."""

import os
import re
from typing import Any, Dict, Optional
import httpx
import openai

from ...shared.mcp_server import BaseMCPServer, ToolResult
from ...shared.redis_client import RedisClientManager
from ...shared.postgres_client import PostgreSQLClientManager
from ...shared.logger import get_logger
from .handlers import (
    analyze_query,
    route_to_agents,
    call_agent_tool,
    synthesize_response,
    execute_query,
    generate_mermaid,
)

logger = get_logger(__name__)


class OrchestratorService(BaseMCPServer):
    """MCP Server for orchestration and coordination."""
    
    def __init__(self):
        super().__init__(
            service_name="OrchestratorService",
            host=os.getenv("ORCHESTRATOR_HOST", "0.0.0.0"),
            port=int(os.getenv("ORCHESTRATOR_PORT", 8001))
        )
        self.redis_client: RedisClientManager = None
        self.postgres_client: PostgreSQLClientManager = None
        self.memory_service_url = os.getenv("MEMORY_SERVICE_URL", "http://memory_service:8005")
        self.graph_service_url = os.getenv("GRAPH_QUERY_SERVICE_URL", "http://graph_query_service:8003")
        self.analyst_service_url = os.getenv("CODE_ANALYST_SERVICE_URL", "http://code_analyst_service:8004")
        self.indexer_service_url = os.getenv("INDEXER_SERVICE_URL", "http://indexer_service:8002")
        self.http_client: httpx.AsyncClient = None
        self.openai_api_key = os.getenv("OPENAI_API_KEY")
    
    @property
    def agent_urls(self) -> Dict[str, str]:
        """Get mapping of agent names to URLs."""
        return {
            "graph_query": self.graph_service_url,
            "code_analyst": self.analyst_service_url,
            "indexer": self.indexer_service_url,
            "memory": self.memory_service_url
        }
    
    async def register_tools(self):
        """Register all orchestration tools."""
        
        # PRIMARY TOOL - Main entry point from Gateway
        self.register_tool(
            name="execute_query",
            description="Main orchestration: analyze query → route to agents → synthesize response",
            input_schema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "User query to process"},
                    "session_id": {"type": "string", "description": "Optional session ID for context"}
                },
                "required": ["query"]
            },
            handler=self._execute_query_handler
        )
        
        # Supporting tools (for inter-agent communication if needed)
        self.register_tool(
            name="analyze_query",
            description="[Internal] Classify query intent and extract entities",
            input_schema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Query to analyze"}
                },
                "required": ["query"]
            },
            handler=self._analyze_query_handler
        )
        
        self.register_tool(
            name="route_to_agents",
            description="[Internal] Determine which agents to call",
            input_schema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "User query"},
                    "intent": {"type": "string", "description": "Detected intent"}
                },
                "required": ["query", "intent"]
            },
            handler=self._route_to_agents_handler
        )
        
        self.register_tool(
            name="call_agent_tool",
            description="[Internal] Call a tool on remote agent",
            input_schema={
                "type": "object",
                "properties": {
                    "agent": {"type": "string", "enum": ["graph_query", "code_analyst", "indexer"]},
                    "tool": {"type": "string", "description": "Tool name"},
                    "input": {"type": "object", "description": "Tool parameters"}
                },
                "required": ["agent", "tool", "input"]
            },
            handler=self._call_agent_tool_handler
        )
        
        self.register_tool(
            name="synthesize_response",
            description="[Internal] Combine agent results into final response",
            input_schema={
                "type": "object",
                "properties": {
                    "agent_results": {"type": "array", "description": "Results from agents"},
                    "original_query": {"type": "string", "description": "Original query"}
                },
                "required": ["agent_results", "original_query"]
            },
            handler=self._synthesize_response_handler
        )
        
        self.register_tool(
            name="generate_mermaid",
            description="Generate Mermaid diagram from Neo4j query results",
            input_schema={
                "type": "object",
                        "properties": {
                            "query_results": {
                                "type": "array",
                                "description": "Query results from Neo4j"
                            },
                            "entity_name": {
                                "type": "string",
                                "description": "Central entity name"
                            },
                            "entity_type": {
                                "type": "string",
                                "description": "Entity type (Class, Function, etc)"
                            }
                        },
                        "required": ["query_results", "entity_name", "entity_type"]
                    },
                    handler=self._generate_mermaid_handler
                )
                
        self.logger.info("✅ Registered 6 orchestration tools (execute_query + 5 internal)")    
    # ========================================================================
    # HANDLER WRAPPERS - Bridge between FastAPI endpoints and handler logic
    # ========================================================================
    
    async def _execute_query_handler(self, query: str, session_id: str = None) -> ToolResult:
        """Wrapper for execute_query handler."""
        return await execute_query(
            query=query,
            session_id=session_id,
            openai_api_key=self.openai_api_key,
            http_client=self.http_client,
            postgres_client=self.postgres_client,
            agent_urls=self.agent_urls
        )
    
    async def _analyze_query_handler(self, query: str) -> ToolResult:
        """Wrapper for analyze_query handler."""
        return await analyze_query(
            query=query,
            openai_api_key=self.openai_api_key
        )
    
    async def _route_to_agents_handler(self, query: str, intent: str) -> ToolResult:
        """Wrapper for route_to_agents handler."""
        return await route_to_agents(
            query=query,
            intent=intent
        )
    
    async def _call_agent_tool_handler(self, agent: str, tool: str, input: Dict[str, Any]) -> ToolResult:
        """Wrapper for call_agent_tool handler."""
        return await call_agent_tool(
            agent=agent,
            tool=tool,
            input_params=input,
            http_client=self.http_client,
            agent_urls=self.agent_urls
        )
    
    async def _synthesize_response_handler(self, agent_results: list, original_query: str) -> ToolResult:
        """Wrapper for synthesize_response handler."""
        return await synthesize_response(
            agent_results=agent_results,
            original_query=original_query
        )

    async def _generate_mermaid_handler(self, query_results: list, entity_name: str, entity_type: str) -> ToolResult:
        """Wrapper for generate_mermaid handler."""
        return await generate_mermaid(
            query_results=query_results,
            entity_name=entity_name,
            entity_type=entity_type
        )
    
    def _select_tool_for_agent(self, agent_name: str, intent: str, entities: list) -> str:
        """
        Select appropriate tool for agent based on intent.
        
        Args:
            agent_name: Name of agent (graph_query, code_analyst, indexer)
            intent: Query intent (search, explain, analyze, etc.)
            entities: Extracted entities from query
            
        Returns:
            Tool name to call on agent
        """
        # Agent-to-tool mapping
        agent_tools = {
            "graph_query": {
                "search": "find_entity",
                "explain": "find_entity",
                "analyze": "find_entity",
                "list": "find_entity",
                "default": "find_entity"
            },
            "code_analyst": {
                "explain": "analyze_function",
                "analyze": "analyze_class",
                "default": "analyze_function"
            },
            "indexer": {
                "index": "index_repository",
                "embed": "embed_repository",
                "status": "get_index_status",
                "default": "get_index_status"
            }
        }
        
        # Get tool for agent and intent
        agent_tools_map = agent_tools.get(agent_name, {})
        tool = agent_tools_map.get(intent, agent_tools_map.get("default"))
        
        self.logger.debug(f"Selected tool {tool} for agent {agent_name} with intent {intent}")
        return tool

    def _prepare_agent_input(self, agent_name: str, tool_name: str, query: str, entities: list) -> Dict[str, Any]:
        """
        Prepare input parameters for agent tool call.
        
        Args:
            agent_name: Name of agent
            tool_name: Tool to call
            query: Original user query
            entities: Extracted entities
            
        Returns:
            Input dictionary for tool
        """
        # Default entity to search for (first extracted entity or "main")
        entity_name = entities[0] if entities else "main"
        
        # Tool-specific input preparation
        if tool_name == "find_entity":
            return {"name": entity_name, "entity_type": None}
        elif tool_name == "analyze_function":
            return {"name": entity_name}
        elif tool_name == "analyze_class":
            return {"name": entity_name}
        elif tool_name == "index_repository":
            # Extract repo URL from query if possible
            repo_url = self._extract_repo_url(query)
            return {"repo_url": repo_url or "https://github.com/tiangolo/fastapi", "branch": "main"}
        elif tool_name == "get_index_status":
            return {}
        else:
            return {}

    def _extract_repo_url(self, query: str) -> str:
        """
        Extract GitHub URL from query if present.
        
        Args:
            query: User query text
            
        Returns:
            GitHub URL if found, None otherwise
        """
        import re
        match = re.search(r'https://github\.com/[\w\-]+/[\w\-]+', query)
        return match.group(0) if match else None

    async def _store_conversation(
        self,
        session_id: str,
        query: str,
        response: str,
        agents_used: list,
        intent: str
    ) -> None:
        """
        Store conversation in PostgreSQL via Memory Service.
        
        Args:
            session_id: Conversation session ID
            query: User query
            response: AI response
            agents_used: List of agents that responded
            intent: Detected intent
        """
        try:
            # Store user turn
            await self.execute_tool("store_turn", {
                "session_id": session_id,
                "turn_number": 1,
                "role": "user",
                "content": query
            })
            
            # Store assistant turn
            await self.execute_tool("store_turn", {
                "session_id": session_id,
                "turn_number": 2,
                "role": "assistant",
                "content": response
            })
            
            self.logger.info(f"Stored conversation turns for session {session_id}")
            
        except Exception as e:
            self.logger.error(f"Failed to store conversation: {e}")
            raise
    async def _setup_service(self):
        """Initialize Redis, PostgreSQL, HTTP client, and OpenAI."""
        try:
            redis_url = os.getenv("REDIS_URL", "redis://:redis_password@localhost:6379/0")
            self.redis_client = RedisClientManager(redis_url)
            
            db_url = os.getenv("DATABASE_URL", "postgresql://postgres:postgres_password@localhost:5432/codebase_chat")
            if db_url.startswith("postgresql://"):
                db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)
            
            self.postgres_client = PostgreSQLClientManager(db_url)
            await self.postgres_client.initialize()
            
            self.http_client = httpx.AsyncClient(timeout=30.0)
            openai.api_key = self.openai_api_key
            
            self.logger.info("Orchestrator Service initialized successfully")
        except Exception as e:
            self.logger.error(f"Failed to initialize orchestrator service: {e}")
            raise
    
    async def _cleanup_service(self):
        """Cleanup services."""
        if self.http_client:
            await self.http_client.aclose()
        if self.postgres_client:
            await self.postgres_client.close()
        if self.redis_client:
            self.redis_client.close()
