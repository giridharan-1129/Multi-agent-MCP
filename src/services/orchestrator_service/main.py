"""
Orchestrator Service - MCP Server for multi-agent orchestration.

Responsibilities:
- Analyze incoming queries and determine which agents to invoke
- Manage conversation context and memory
- Coordinate parallel or sequential agent calls
- Synthesize final responses from multiple agent outputs
- Handle fallback strategies when agents fail
"""

import os
import asyncio
import hashlib
from typing import Any, Dict, List, Optional
from datetime import datetime
from uuid import UUID

from fastapi import FastAPI, HTTPException
import httpx

from ...shared.mcp_server import BaseMCPServer, ToolResult
from ...shared.redis_client import RedisClientManager
from ...shared.postgres_client import PostgreSQLClientManager
from ...shared.logger import get_logger

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
    
    async def register_tools(self):
        """Register orchestration tools."""
        
        # Tool 1: Analyze Query
        self.register_tool(
            name="analyze_query",
            description="Classify query intent and extract key entities",
            input_schema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "User query to analyze"
                    }
                },
                "required": ["query"]
            },
            handler=self.analyze_query_handler
        )
        
        # Tool 2: Route to Agents
        self.register_tool(
            name="route_to_agents",
            description="Determine which agents should handle the query",
            input_schema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "User query"
                    },
                    "intent": {
                        "type": "string",
                        "description": "Classified intent (search, analyze, explain, etc)"
                    }
                },
                "required": ["query", "intent"]
            },
            handler=self.route_to_agents_handler
        )
        
        # Tool 3: Get Conversation Context
        self.register_tool(
            name="get_conversation_context",
            description="Retrieve relevant conversation history",
            input_schema={
                "type": "object",
                "properties": {
                    "session_id": {
                        "type": "string",
                        "description": "Session UUID"
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Number of recent turns to retrieve"
                    }
                },
                "required": ["session_id"]
            },
            handler=self.get_conversation_context_handler
        )
        
        # Tool 4: Call Agent Tool
        self.register_tool(
            name="call_agent_tool",
            description="Call a specific tool on a remote agent service",
            input_schema={
                "type": "object",
                "properties": {
                    "agent": {
                        "type": "string",
                        "enum": ["graph_query", "code_analyst", "indexer", "memory"],
                        "description": "Agent service name"
                    },
                    "tool": {
                        "type": "string",
                        "description": "Tool name to execute"
                    },
                    "input": {
                        "type": "object",
                        "description": "Tool input parameters"
                    }
                },
                "required": ["agent", "tool", "input"]
            },
            handler=self.call_agent_tool_handler
        )
        
        # Tool 5: Synthesize Response
        self.register_tool(
            name="synthesize_response",
            description="Combine agent outputs into coherent response",
            input_schema={
                "type": "object",
                "properties": {
                    "agent_results": {
                        "type": "array",
                        "description": "Results from multiple agents"
                    },
                    "original_query": {
                        "type": "string",
                        "description": "Original user query"
                    }
                },
                "required": ["agent_results", "original_query"]
            },
            handler=self.synthesize_response_handler
        )
        
        # Tool 6: Store Agent Response
        self.register_tool(
            name="store_agent_response",
            description="Log agent response to conversation memory",
            input_schema={
                "type": "object",
                "properties": {
                    "turn_id": {
                        "type": "string",
                        "description": "Turn UUID"
                    },
                    "agent_name": {
                        "type": "string",
                        "description": "Agent name"
                    },
                    "tools_used": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Tools used by agent"
                    },
                    "result": {
                        "type": "string",
                        "description": "Agent result"
                    }
                },
                "required": ["turn_id", "agent_name", "result"]
            },
            handler=self.store_agent_response_handler
        )
        
        self.logger.info("Registered 6 orchestration tools")
    
    async def _setup_service(self):
        """Initialize Redis, PostgreSQL, and HTTP client."""
        try:
            redis_url = os.getenv("REDIS_URL", "redis://:redis_password@localhost:6379/0")
            self.redis_client = RedisClientManager(redis_url)
            
            db_url = os.getenv("DATABASE_URL", "postgresql://postgres:postgres_password@localhost:5432/codebase_chat")
            if db_url.startswith("postgresql://"):
                db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)
            
            self.postgres_client = PostgreSQLClientManager(db_url)
            await self.postgres_client.initialize()
            
            self.http_client = httpx.AsyncClient(timeout=30.0)
            
            self.logger.info("Orchestrator Service initialized successfully")
        except Exception as e:
            self.logger.error(f"Failed to initialize orchestrator service: {e}")
            raise
    
    # ============================================================================
    # TOOL HANDLERS
    # ============================================================================
    
    async def analyze_query_handler(self, query: str) -> ToolResult:
        """Handle analyze_query tool."""
        try:
            # Simple intent classification based on keywords
            query_lower = query.lower()
            
            intents = {
                "search": ["find", "locate", "search", "where", "what is"],
                "explain": ["explain", "how does", "how is", "describe", "tell me about"],
                "analyze": ["analyze", "compare", "difference", "similar"],
                "list": ["list", "show", "get all", "what are"],
                "implement": ["implement", "build", "create", "write"]
            }
            
            detected_intent = "search"
            for intent, keywords in intents.items():
                if any(kw in query_lower for kw in keywords):
                    detected_intent = intent
                    break
            
            # Extract entities (simple regex-based)
            entities = []
            words = query.split()
            for word in words:
                if word[0].isupper() and len(word) > 2:
                    entities.append(word)
            
            return ToolResult(
                success=True,
                data={
                    "query": query,
                    "intent": detected_intent,
                    "entities": entities,
                    "confidence": 0.8
                }
            )
        except Exception as e:
            self.logger.error(f"Failed to analyze query: {e}")
            return ToolResult(success=False, error=str(e))
    
    async def route_to_agents_handler(
        self,
        query: str,
        intent: str
    ) -> ToolResult:
        """Handle route_to_agents tool."""
        try:
            routing = {
                "search": ["graph_query"],
                "explain": ["graph_query", "code_analyst"],
                "analyze": ["code_analyst", "graph_query"],
                "list": ["graph_query"],
                "implement": ["indexer"]
            }
            
            agents = routing.get(intent, ["graph_query"])
            
            return ToolResult(
                success=True,
                data={
                    "query": query,
                    "intent": intent,
                    "recommended_agents": agents,
                    "parallel": len(agents) > 1
                }
            )
        except Exception as e:
            self.logger.error(f"Failed to route to agents: {e}")
            return ToolResult(success=False, error=str(e))
    
    async def get_conversation_context_handler(
        self,
        session_id: str,
        limit: int = 5
    ) -> ToolResult:
        """Handle get_conversation_context tool."""
        try:
            session_uuid = UUID(session_id)
            history = await self.postgres_client.get_conversation_history(session_uuid, limit)
            
            context_turns = [
                {
                    "turn_number": turn.turn_number,
                    "role": turn.role,
                    "content": turn.content[:300]  # Truncate
                }
                for turn in history
            ]
            
            return ToolResult(
                success=True,
                data={
                    "session_id": session_id,
                    "context": context_turns
                }
            )
        except Exception as e:
            self.logger.error(f"Failed to get conversation context: {e}")
            return ToolResult(success=False, error=str(e))
    
    async def call_agent_tool_handler(
        self,
        agent: str,
        tool: str,
        input: Dict[str, Any]
    ) -> ToolResult:
        """Handle call_agent_tool tool."""
        try:
            # Map agent name to URL
            agent_urls = {
                "graph_query": self.graph_service_url,
                "code_analyst": self.analyst_service_url,
                "indexer": self.indexer_service_url,
                "memory": self.memory_service_url
            }
            
            url = agent_urls.get(agent)
            if not url:
                return ToolResult(success=False, error=f"Unknown agent: {agent}")
            
            # Call agent service
            execute_url = f"{url}/execute?tool_name={tool}"
            
            response = await self.http_client.post(
                execute_url,
                json=input,
                timeout=30.0
            )
            
            if response.status_code != 200:
                return ToolResult(
                    success=False,
                    error=f"Agent call failed: {response.text}"
                )
            
            result = response.json()
            
            return ToolResult(
                success=result.get("success", False),
                data=result.get("data"),
                error=result.get("error")
            )
        except Exception as e:
            self.logger.error(f"Failed to call agent tool: {e}")
            return ToolResult(success=False, error=str(e))
    
    async def synthesize_response_handler(
        self,
        agent_results: List[Dict[str, Any]],
        original_query: str
    ) -> ToolResult:
        """Handle synthesize_response tool."""
        try:
            # Combine results into coherent response
            synthesis = f"Based on analysis of '{original_query}':\n\n"
            
            for result in agent_results:
                agent_name = result.get("agent", "Unknown")
                data = result.get("data", {})
                synthesis += f"**{agent_name}:** {data}\n\n"
            
            return ToolResult(
                success=True,
                data={
                    "synthesis": synthesis.strip(),
                    "num_agents": len(agent_results)
                }
            )
        except Exception as e:
            self.logger.error(f"Failed to synthesize response: {e}")
            return ToolResult(success=False, error=str(e))
    
    async def store_agent_response_handler(
        self,
        turn_id: str,
        agent_name: str,
        result: str,
        tools_used: List[str] = None
    ) -> ToolResult:
        """Handle store_agent_response tool."""
        try:
            turn_uuid = UUID(turn_id)
            response = await self.postgres_client.store_agent_response(
                turn_uuid,
                agent_name,
                tools_used or [],
                result
            )
            
            return ToolResult(
                success=True,
                data={
                    "response_id": str(response.id),
                    "agent_name": response.agent_name
                }
            )
        except Exception as e:
            self.logger.error(f"Failed to store agent response: {e}")
            return ToolResult(success=False, error=str(e))
    
    async def _cleanup_service(self):
        """Cleanup services."""
        if self.http_client:
            await self.http_client.aclose()
        if self.postgres_client:
            await self.postgres_client.close()
        if self.redis_client:
            self.redis_client.close()


# ============================================================================
# FASTAPI APP
# ============================================================================

app = FastAPI(title="Orchestrator Service", version="1.0.0")
orchestrator_service: OrchestratorService = None


@app.on_event("startup")
async def startup():
    """Initialize orchestrator service."""
    global orchestrator_service
    orchestrator_service = OrchestratorService()
    await orchestrator_service.initialize()


@app.on_event("shutdown")
async def shutdown():
    """Cleanup on shutdown."""
    if orchestrator_service:
        await orchestrator_service.shutdown()


@app.get("/health")
async def health():
    """Health check endpoint."""
    if not orchestrator_service:
        raise HTTPException(status_code=503, detail="Service not initialized")
    
    pg_healthy = await orchestrator_service.postgres_client.health_check()
    redis_healthy = await orchestrator_service.redis_client.health_check()
    
    if not (pg_healthy and redis_healthy):
        raise HTTPException(status_code=503, detail="Backend connection failed")
    
    return {
        "status": "healthy",
        "service": "OrchestratorService",
        "postgres": "ok" if pg_healthy else "error",
        "redis": "ok" if redis_healthy else "error",
        "tools": len(orchestrator_service.tools)
    }


@app.get("/tools")
async def get_tools():
    """Get available tools schema."""
    if not orchestrator_service:
        raise HTTPException(status_code=503, detail="Service not initialized")
    
    return {
        "service": "OrchestratorService",
        "tools": orchestrator_service.get_tools_schema()
    }


@app.post("/execute")
async def execute_tool(tool_name: str, tool_input: Dict[str, Any]):
    """Execute a tool."""
    if not orchestrator_service:
        raise HTTPException(status_code=503, detail="Service not initialized")
    
    result = await orchestrator_service.execute_tool(tool_name, tool_input)
    return result.dict()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app,
        host=os.getenv("ORCHESTRATOR_HOST", "0.0.0.0"),
        port=int(os.getenv("ORCHESTRATOR_PORT", 8001))
    )
