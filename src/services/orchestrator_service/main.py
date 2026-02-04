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
import json
from typing import Any, Dict, List, Optional
from datetime import datetime
from uuid import UUID

from fastapi import FastAPI, HTTPException
import httpx
import openai

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

        # Tool 7: Generate Mermaid Diagram
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
            handler=self.generate_mermaid_handler
        )
       # Tool 7: Call Agent Tool (UPDATE - add call_agent_tool)
        self.register_tool(
            name="call_agent_tool",
            description="Call a specific tool on a remote agent service",
            input_schema={
                "type": "object",
                "properties": {
                    "agent": {
                        "type": "string",
                        "enum": ["indexer", "graph_query", "code_analyst"],
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
        
        self.logger.info("Registered 7 orchestration tools") 
        self.register_tool(
            name="execute_query",
            description="Execute a user query - orchestrates all agents",
            input_schema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "User query to process"
                    },
                    "session_id": {
                        "type": "string",
                        "description": "Optional session ID for context"
                    }
                },
                "required": ["query"]
            },
            handler=self.execute_query_handler
        )
        
        self.logger.info("Registered 7 orchestration tools")    

    async def execute_query_handler(
            self,
            query: str,
            session_id: str = None
        ) -> ToolResult:
            """
            Handle execute_query tool - Main orchestration flow.
            
            Flow:
            1. Analyze query intent
            2. Route to appropriate agents
            3. Call agents in parallel/sequence
            4. Synthesize results
            5. Store conversation
            6. Return response
            """
            try:
                self.logger.info("=" * 80)
                self.logger.info(f"📋 ORCHESTRATOR: New query received")
                self.logger.info(f"   Query: {query[:100]}...")
                self.logger.info(f"   Session: {session_id or 'NEW'}")
                self.logger.info("=" * 80)
                
                # Step 1: Analyze query
                self.logger.info("🔍 STEP 1: Analyzing query intent with GPT-4...")
                analysis = await self.analyze_query_handler(query)
                
                if not analysis.success:
                    self.logger.error(f"❌ Query analysis failed: {analysis.error}")
                    return ToolResult(success=False, error="Query analysis failed")
                
                intent = analysis.data.get("intent", "search")
                entities = analysis.data.get("entities", [])
                confidence = analysis.data.get("confidence", 0)
                
                self.logger.info(f"   ✓ Intent: {intent} (confidence: {confidence})")
                self.logger.info(f"   ✓ Entities found: {entities}")
                
                # Step 2: Route to agents
                self.logger.info("🛣️  STEP 2: Routing to appropriate agents...")
                routing = await self.route_to_agents_handler(query, intent)
                
                if not routing.success:
                    self.logger.error(f"❌ Agent routing failed: {routing.error}")
                    return ToolResult(success=False, error="Agent routing failed")
                
                agent_names = routing.data.get("recommended_agents", ["graph_query"])
                parallel = routing.data.get("parallel", False)
                
                self.logger.info(f"   ✓ Agents to call: {agent_names}")
                self.logger.info(f"   ✓ Execution mode: {'Parallel' if parallel else 'Sequential'}")
                
                # Step 3: Call agents
                self.logger.info("🤖 STEP 3: Calling agents...")
                agent_results = []
                
                for agent_idx, agent_name in enumerate(agent_names, 1):
                    self.logger.info(f"\n   [{agent_idx}/{len(agent_names)}] Calling agent: {agent_name}")
                    
                    # Map agent name to tool selection based on query & intent
                    if agent_name == "indexer":
                        if intent == "index":
                            tool_name = "index_repository"
                            tool_input = {
                                "repo_url": analysis.data.get("repo_url", ""),
                                "branch": "main"
                            }
                        elif intent == "embed":
                            tool_name = "embed_repository"
                            repo_url = analysis.data.get("repo_url", "")
                            repo_id = repo_url.split("/")[-1].replace(".git", "") if repo_url else "repo"
                            tool_input = {
                                "repo_url": repo_url,
                                "repo_id": repo_id,
                                "branch": "main"
                            }
                        else:
                            tool_name = "get_index_status"
                            tool_input = {}
                    elif agent_name == "graph_query":
                        tool_name = "find_entity"
                        tool_input = {
                            "name": entities[0] if entities else query.split()[0]
                        }
                    elif agent_name == "code_analyst":
                        tool_name = "analyze_function"
                        tool_input = {
                            "name": entities[0] if entities else "main"
                        }
                    else:
                        tool_name = "get_index_status"
                        tool_input = {}
                    
                    self.logger.info(f"      → Executing {agent_name}/{tool_name}...")
                    
                    agent_call = await self.call_agent_tool_handler(
                        agent=agent_name,
                        tool=tool_name,
                        input=tool_input
                    )
                    
                    if agent_call.success:
                        self.logger.info(f"      ✓ Agent succeeded")
                    else:
                        self.logger.error(f"      ❌ Agent failed: {agent_call.error}")
                    
                    agent_results.append({
                        "agent": agent_name,
                        "data": agent_call.data if agent_call.success else {"error": agent_call.error}
                    })
                
                # Step 4: Synthesize response
                # Step 4: Synthesize response
                self.logger.info("🔗 STEP 4: Synthesizing results...")
                self.logger.info(f"   Agent results: {len(agent_results)} responses to synthesize")
                
                synthesis = await self.synthesize_response_handler(agent_results, query)
                
                if not synthesis.success:
                    self.logger.error(f"❌ Response synthesis failed: {synthesis.error}")
                    return ToolResult(success=False, error="Response synthesis failed")
                
                response_text = synthesis.data.get("response", "No response generated")
                agents_used = synthesis.data.get("agents_used", [])
                
                self.logger.info(f"   ✓ Response synthesized")
                self.logger.info(f"   ✓ Agents involved: {agents_used}")
                self.logger.info(f"   ✓ Response length: {len(response_text)} chars")
                
                # Step 5: Store conversation in Memory Service
                self.logger.info("💾 STEP 5: Storing conversation in Memory Service...")
                session_uuid = None
                try:
                    if not session_id:
                        self.logger.debug("   No session provided, creating new session")
                        session_id = str(UUID(int=0))  # Fallback session
                    
                    session_uuid = UUID(session_id) if isinstance(session_id, str) else session_id
                    self.logger.debug(f"   Session UUID: {session_uuid}")
                    
                    # Get or create session
                    existing_session = await self.postgres_client.get_session(session_uuid)
                    if not existing_session:
                        existing_session = await self.postgres_client.create_session(
                            user_id="anonymous",
                            session_name=f"Query: {query[:50]}"
                        )
                        session_uuid = existing_session.id
                    
                    # Get current turn count
                    history = await self.postgres_client.get_conversation_history(session_uuid, limit=1)
                    turn_number = len(history) + 1
                    
                    # Store user query
                    user_turn = await self.postgres_client.store_turn(
                        session_id=session_uuid,
                        turn_number=turn_number,
                        role="user",
                        content=query
                    )
                    
                    # Store assistant response
                    assistant_turn = await self.postgres_client.store_turn(
                        session_id=session_uuid,
                        turn_number=turn_number + 1,
                        role="assistant",
                        content=response_text
                    )
                    
                    # Store agent response metadata
                    await self.postgres_client.store_agent_response(
                        turn_id=assistant_turn.id,
                        agent_name="orchestrator",
                        tools_used=agents_used,
                        result=response_text
                    )
                    
                    self.logger.info(f"Stored conversation in Memory Service: session={session_uuid}")
                except Exception as memory_err:
                    self.logger.warning(f"Failed to store conversation: {memory_err}")
                    # Don't fail the query if memory storage fails
                
                self.logger.info("=" * 80)
                self.logger.info(f"✅ ORCHESTRATION COMPLETE")
                self.logger.info(f"   Status: SUCCESS")
                self.logger.info(f"   Agents: {agents_used}")
                self.logger.info(f"   Session: {session_uuid}")
                self.logger.info("=" * 80)
                
                return ToolResult(
                    success=True,
                    data={
                        "response": response_text,
                        "agents_used": agents_used,
                        "intent": intent,
                        "entities_found": entities,
                        "session_id": str(session_uuid) if session_uuid else None
                    }
                )
                
            except Exception as e:
                self.logger.error("=" * 80)
                self.logger.error(f"❌ ORCHESTRATION FAILED")
                self.logger.error(f"   Error: {str(e)}")
                self.logger.error("=" * 80)
                return ToolResult(success=False, error=str(e))
                
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
            
            # Initialize OpenAI
            openai.api_key = os.getenv("OPENAI_API_KEY")
            
            self.logger.info("Orchestrator Service initialized successfully")
        except Exception as e:
            self.logger.error(f"Failed to initialize orchestrator service: {e}")
            raise
    
    # ============================================================================
    # TOOL HANDLERS
    # ============================================================================
    
    async def analyze_query_handler(self, query: str) -> ToolResult:
        """Use GPT-4 to analyze query intent intelligently."""
        try:
            from openai import OpenAI
            client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
            response = client.chat.completions.create(
                model="gpt-4",
                messages=[
                    {
                        "role": "system",
                        "content": """Analyze the user query for a codebase analysis system.
            Return JSON:
            {
            "intent": "search|explain|analyze|index|embed|implement|stats",
            "entities": ["entity1", "entity2"],
            "repo_url": "url if indexing" or null,
            "confidence": 0.0-1.0
            }"""
                    },
                    {"role": "user", "content": query}
                ],
                temperature=0.5,
                max_tokens=200
            )
            
            result_text = response.choices[0].message.content
            
            try:
                analysis = json.loads(result_text)
            except:
                analysis = {
                    "intent": "search",
                    "entities": [],
                    "repo_url": None,
                    "confidence": 0.5
                }
            
            return ToolResult(
                success=True,
                data={
                    "query": query,
                    "intent": analysis.get("intent", "search"),
                    "entities": analysis.get("entities", []),
                    "repo_url": analysis.get("repo_url"),
                    "confidence": analysis.get("confidence", 0.5)
                }
            )
        except Exception as e:
            self.logger.error(f"Failed to analyze query with LLM: {e}")
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
                    "implement": ["indexer"],
                    "index": ["indexer"],
                    "embed": ["indexer"],
                    "stats": ["indexer"],
                    "status": ["indexer"],
                    "query": ["indexer"]
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
        """Handle call_agent_tool tool - calls remote agent service."""
        try:
            self.logger.debug(f"🔗 Calling agent: {agent} | Tool: {tool}")
            
            # Map agent name to URL
            agent_urls = {
                "graph_query": self.graph_service_url,
                "code_analyst": self.analyst_service_url,
                "indexer": self.indexer_service_url,
                "memory": self.memory_service_url
            }
            
            url = agent_urls.get(agent)
            if not url:
                self.logger.error(f"❌ Unknown agent: {agent}")
                return ToolResult(success=False, error=f"Unknown agent: {agent}")
            
            # Build correct HTTP request - tool_name as query param, input as body
            execute_url = f"{url}/execute"
            
            self.logger.debug(f"   URL: {execute_url}")
            self.logger.debug(f"   Input: {input}")

            response = await self.http_client.post(
                execute_url,
                params={"tool_name": tool},  # ← Query parameter, not body
                json=input,  # ← Only actual tool input in body
                timeout=30.0
            )
            
            self.logger.debug(f"   Status: {response.status_code}")
            
            if response.status_code != 200:
                error_msg = response.text
                self.logger.error(f"❌ Agent call failed: {error_msg}")
                return ToolResult(
                    success=False,
                    error=f"Agent call failed: {error_msg}"
                )
            
            result = response.json()
            
            if result.get("success"):
                self.logger.debug(f"   ✓ Agent succeeded")
            else:
                self.logger.warning(f"   ⚠️  Agent returned error: {result.get('error')}")
            
            return ToolResult(
                success=result.get("success", False),
                data=result.get("data"),
                error=result.get("error")
            )
        except Exception as e:
            self.logger.error(f"❌ Failed to call agent tool: {e}")
            return ToolResult(success=False, error=str(e))
    
    async def synthesize_response_handler(
        self,
        agent_results: List[Dict[str, Any]],
        original_query: str
    ) -> ToolResult:
        """Handle synthesize_response tool - combines multiple agent outputs."""
        try:
            if not agent_results:
                return ToolResult(
                    success=True,
                    data={
                        "response": f"Query: {original_query}\n\nNo agent results available.",
                        "agents_used": []
                    }
                )
            
            # Build comprehensive synthesis
            lines = [f"**Query:** {original_query}\n"]
            agents_used = []
            
            for idx, result in enumerate(agent_results, 1):
                agent_name = result.get("agent", result.get("agent_name", "Unknown"))
                data = result.get("data", {})
                agents_used.append(agent_name)
                
                lines.append(f"\n**[{idx}] {agent_name}:**")
                
                # Handle different data formats
                if isinstance(data, dict):
                    if data.get("error"):
                        lines.append(f"Error: {data.get('error')}")
                    else:
                        for key, value in data.items():
                            if value is not None:
                                if isinstance(value, list) and len(value) > 0:
                                    lines.append(f"  • {key}: {', '.join(map(str, value[:5]))}")
                                elif isinstance(value, dict):
                                    lines.append(f"  • {key}: {len(value)} items")
                                else:
                                    lines.append(f"  • {key}: {str(value)[:200]}")
                else:
                    lines.append(f"  {str(data)[:300]}")
            
            return ToolResult(
                success=True,
                data={
                    "response": "\n".join(lines),
                    "agents_used": list(set(agents_used)),
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
    
    async def generate_mermaid_handler(
        self,
        query_results: List[Dict[str, Any]],
        entity_name: str,
        entity_type: str
    ) -> ToolResult:
        """Handle generate_mermaid tool."""
        try:
            # Extract relationships from results
            nodes = set()
            edges = []
            
            # Add central node
            nodes.add(entity_name)
            
            # Parse results for relationships
            for result in query_results:
                if isinstance(result, dict):
                    # Look for source/target patterns
                    source = result.get("source") or result.get("source_name")
                    target = result.get("target") or result.get("target_name")
                    rel_type = result.get("relationship_type") or result.get("type")
                    
                    if source and target:
                        nodes.add(source)
                        nodes.add(target)
                        edges.append({
                            "source": source,
                            "target": target,
                            "type": rel_type or "RELATES"
                        })
            
            # Generate Mermaid syntax
            mermaid_code = f"graph TD\n"
            
            # Add nodes with styling
            for node in nodes:
                if node == entity_name:
                    mermaid_code += f'    {node}["{node}<br/><b>{entity_type}</b>"]:::primary\n'
                else:
                    mermaid_code += f'    {node}["{node}"]\n'
            
            # Add edges with labels
            for edge in edges:
                source = edge["source"]
                target = edge["target"]
                rel_type = edge["type"]
                mermaid_code += f'    {source} -->|{rel_type}| {target}\n'
            
            # Add styling
            mermaid_code += '\n    classDef primary fill:#FF6B6B,stroke:#FF5252,color:#fff\n'
            
            return ToolResult(
                success=True,
                data={
                    "mermaid_code": mermaid_code,
                    "nodes_count": len(nodes),
                    "edges_count": len(edges)
                }
            )
        except Exception as e:
            self.logger.error(f"Failed to generate mermaid: {e}")
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
async def execute_tool(tool_input: Dict[str, Any]):
    """Execute a tool - intelligently identifies tool from input."""
    if not orchestrator_service:
        raise HTTPException(status_code=503, detail="Service not initialized")
    
    # Intelligently identify tool from input
    tool_name = _identify_tool(tool_input)
    
    if not tool_name:
        raise HTTPException(status_code=400, detail="Could not identify tool from input")
    
    # Extract actual tool input (remove tool_name if present)
    actual_input = {k: v for k, v in tool_input.items() if k != "tool_name"}
    
    result = await orchestrator_service.execute_tool(tool_name, actual_input)
    return {
        "success": result.success,
        "data": result.data,
        "error": result.error
    }


def _identify_tool(tool_input: Dict[str, Any]) -> Optional[str]:
    """Intelligently identify which tool to call based on input keys - checks in order of specificity."""
    
    # List of (tool_name, required_keys) ordered by specificity (most specific first)
    # This ensures tools with specific keys match BEFORE tools with no keys
    tool_patterns = [
        ("execute_query", ["query"]),
        ("synthesize_response", ["agent_results", "original_query"]),
        ("store_agent_response", ["turn_id", "agent_name", "result"]),
        ("generate_mermaid", ["query_results", "entity_name", "entity_type"]),
        ("call_agent_tool", ["agent", "tool", "input"]),
        ("route_to_agents", ["query", "intent"]),
        ("get_conversation_context", ["session_id"]),
        ("analyze_query", ["query"]),
        ("find_entity", ["name"]),
        ("index_repository", ["repo_url", "branch"]),
        # Fallback tools - only match with empty input
        ("get_index_status", []),
        ("clear_index", []),
    ]
    
    input_keys = set(tool_input.keys())
    
    # Check patterns in order - more specific first
    for tool_name, required_keys in tool_patterns:
        if required_keys:
            # Require ALL keys to be present
            if all(key in input_keys for key in required_keys):
                return tool_name
        else:
            # Fallback tools - only match if input is completely empty
            if len(input_keys) == 0:
                return tool_name
    
    return None

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app,
        host=os.getenv("ORCHESTRATOR_HOST", "0.0.0.0"),
        port=int(os.getenv("ORCHESTRATOR_PORT", 8001))
    )