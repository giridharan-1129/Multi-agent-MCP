"""
Orchestrator Agent - Central coordinator for multi-agent system.

WHAT: Central MCP agent that coordinates other agents
WHY: Route queries to appropriate agents, manage conversation context, synthesize responses
HOW: Analyze query intent, call relevant agents, combine results

Example:
    agent = OrchestratorAgent()
    await agent.startup()
    
    result = await agent.execute_tool("analyze_query", {
        "query": "How does FastAPI handle dependency injection?",
        "session_id": "user-123"
    })
"""
import os
import json
from openai import OpenAI

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import uuid4
from ..shared.base_agent import BaseAgent
from ..shared.logger import get_logger
from ..shared.mcp_types import (
    MCPTool,
    ToolResult,
    ToolParameter,
    ToolDefinition,
    QueryAnalysis,
    ConversationMessage,
    ConversationContext,
)

logger = get_logger(__name__)


class AnalyzeQueryTool(MCPTool):
    """Tool to analyze user queries."""

    name: str = "analyze_query"
    description: str = "Analyze a user query to determine intent and required agents"

    category: str = "orchestration"

    async def execute(self, query: str, session_id: str) -> ToolResult:
        """
        Analyze user query using LLM to extract intent and entities.
        Falls back to rule-based logic if LLM fails.
        """
        logger.info(
            "Starting LLM-based query analysis",
            session_id=session_id,
            query=query,
        )

        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

        system_prompt = (
            "You are an intent classifier for a FastAPI codebase assistant.\n\n"
            "Return ONLY valid JSON with the following schema:\n"
            "{\n"
            '  "intent": "graph_query | code_explanation | dependency_analysis | indexing | general",\n'
            '  "primary_agent": "graph_query | code_analyst | indexer",\n'
            '  "secondary_agents": ["graph_query", "code_analyst"],\n'
            '  "entities": {\n'
            '    "classes": [],\n'
            '    "functions": [],\n'
            '    "modules": []\n'
            "  }\n"
            "}\n\n"
            "Do not include markdown. Do not include explanations."
        )

        try:
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": query},
                ],
                temperature=0,
            )

            content = response.choices[0].message.content
            analysis = json.loads(content)

            logger.info(
                "LLM intent analysis successful",
                session_id=session_id,
                analysis=analysis,
            )

            return ToolResult(
                success=True,
                data=analysis,
            )

        except Exception as e:
            logger.error(
                "LLM intent analysis failed, falling back to rule-based analysis",
                session_id=session_id,
                error=str(e),
            )

            # 🔁 RULE-BASED FALLBACK (SAFE DEFAULT)
            fallback_analysis = {
                "intent": "general",
                "primary_agent": "graph_query",
                "secondary_agents": [],
                "entities": {
                    "classes": [],
                    "functions": [],
                    "modules": [],
                },
            }

            return ToolResult(
                success=True,
                data=fallback_analysis,
            )

    def get_definition(self) -> ToolDefinition:
        """Get tool definition."""
        return ToolDefinition(
            name=self.name,
            description=self.description,
            parameters=[
                ToolParameter(
                    name="query",
                    description="User query to analyze",
                    type="string",
                    required=True,
                ),
                ToolParameter(
                    name="session_id",
                    description="Optional session ID for context tracking",
                    type="string",
                    required=False,
                ),
            ],
            category=self.category,
        )


class CreateConversationTool(MCPTool):
    """Tool to create a new conversation session."""

    name: str = "create_conversation"
    description: str = "Create a new conversation session"
    category: str = "orchestration"

    # In-memory conversation storage (would use database in production)
    conversations: Dict[str, ConversationContext] = {}

    async def execute(self, user_id: Optional[str] = None) -> ToolResult:
        """
        Create a conversation.

        Args:
            user_id: Optional user ID

        Returns:
            ToolResult with session ID
        """
        try:
            session_id = str(uuid4())
            now = datetime.utcnow().isoformat()

            context = ConversationContext(
                session_id=session_id,
                messages=[],
                user_info={"user_id": user_id} if user_id else None,
                created_at=now,
                last_updated=now,
            )

            self.conversations[session_id] = context

            logger.info(
                "Conversation created",
                session_id=session_id,
                user_id=user_id,
            )

            return ToolResult(
                success=True,
                data={
                    "session_id": session_id,
                    "created_at": now,
                },
            )

        except Exception as e:
            logger.error("Failed to create conversation", error=str(e))
            return ToolResult(
                success=False,
                error=str(e),
            )

    def get_definition(self) -> ToolDefinition:
        """Get tool definition."""
        return ToolDefinition(
            name=self.name,
            description=self.description,
            parameters=[
                ToolParameter(
                    name="user_id",
                    description="Optional user ID",
                    type="string",
                    required=False,
                ),
            ],
            category=self.category,
        )


class GetConversationContextTool(MCPTool):
    """Tool to get conversation context."""

    name: str = "get_conversation_context"
    description: str = "Get conversation history and context"
    category: str = "orchestration"

    # Reference to conversations (would be shared state in production)
    conversations: Dict[str, ConversationContext] = {}

    async def execute(self, session_id: str) -> ToolResult:
        """
        Get conversation context.

        Args:
            session_id: Session ID

        Returns:
            ToolResult with conversation context
        """
        try:
            if session_id not in self.conversations:
                return ToolResult(
                    success=False,
                    error=f"Session '{session_id}' not found",
                )

            context = self.conversations[session_id]

            logger.info(
                "Conversation context retrieved",
                session_id=session_id,
                messages=len(context.messages),
            )

            return ToolResult(
                success=True,
                data=context.dict(),
            )

        except Exception as e:
            logger.error("Failed to get conversation context", error=str(e))
            return ToolResult(
                success=False,
                error=str(e),
            )

    def get_definition(self) -> ToolDefinition:
        """Get tool definition."""
        return ToolDefinition(
            name=self.name,
            description=self.description,
            parameters=[
                ToolParameter(
                    name="session_id",
                    description="Session ID",
                    type="string",
                    required=True,
                ),
            ],
            category=self.category,
        )


class AddConversationMessageTool(MCPTool):
    """Tool to add message to conversation."""

    name: str = "add_conversation_message"
    description: str = "Add a message to the conversation history"
    category: str = "orchestration"

    conversations: Dict[str, ConversationContext] = {}

    async def execute(
        self,
        session_id: str,
        role: str,
        content: str,
        agent_name: Optional[str] = None,
    ) -> ToolResult:
        """
        Add message to conversation.

        Args:
            session_id: Session ID
            role: Message role (user, assistant, system)
            content: Message content
            agent_name: Optional agent name (if assistant)

        Returns:
            ToolResult
        """
        try:
            if session_id not in self.conversations:
                return ToolResult(
                    success=False,
                    error=f"Session '{session_id}' not found",
                )

            context = self.conversations[session_id]

            message = ConversationMessage(
                role=role,
                content=content,
                timestamp=datetime.utcnow().isoformat(),
                agent_name=agent_name,
            )

            context.messages.append(message)
            context.last_updated = datetime.utcnow().isoformat()
            if agent_name:
                context.last_agent_used = agent_name

            # Keep only last N messages in memory
            max_messages = 50
            if len(context.messages) > max_messages:
                context.messages = context.messages[-max_messages:]

            logger.info(
                "Message added to conversation",
                session_id=session_id,
                role=role,
            )

            return ToolResult(
                success=True,
                data={"message_count": len(context.messages)},
            )

        except Exception as e:
            logger.error("Failed to add message to conversation", error=str(e))
            return ToolResult(
                success=False,
                error=str(e),
            )

    def get_definition(self) -> ToolDefinition:
        """Get tool definition."""
        return ToolDefinition(
            name=self.name,
            description=self.description,
            parameters=[
                ToolParameter(
                    name="session_id",
                    description="Session ID",
                    type="string",
                    required=True,
                ),
                ToolParameter(
                    name="role",
                    description="Message role (user, assistant, system)",
                    type="string",
                    required=True,
                ),
                ToolParameter(
                    name="content",
                    description="Message content",
                    type="string",
                    required=True,
                ),
                ToolParameter(
                    name="agent_name",
                    description="Optional agent name if assistant message",
                    type="string",
                    required=False,
                ),
            ],
            category=self.category,
        )


class SynthesizeResponseTool(MCPTool):
    """Tool to synthesize response from multiple agent outputs."""

    name: str = "synthesize_response"
    description: str = "Combine outputs from multiple agents into a coherent response"
    category: str = "orchestration"

    async def execute(
        self,
        agent_outputs: Dict[str, Any],
        original_query: str,
    ) -> ToolResult:
        """
        Synthesize response.

        Args:
            agent_outputs: Outputs from different agents
            original_query: Original user query

        Returns:
            ToolResult with synthesized response
        """
        try:
            synthesis = {
                "query": original_query,
                "agent_inputs": list(agent_outputs.keys()),
                "synthesis": self._combine_outputs(agent_outputs),
                "sources": list(agent_outputs.keys()),
            }

            logger.info(
                "Response synthesized",
                agents=len(agent_outputs),
            )

            return ToolResult(
                success=True,
                data=synthesis,
            )

        except Exception as e:
            logger.error("Failed to synthesize response", error=str(e))
            return ToolResult(
                success=False,
                error=str(e),
            )

    def _combine_outputs(self, outputs: Dict[str, Any]) -> str:
        """
        Combine outputs from multiple agents.

        Args:
            outputs: Agent outputs

        Returns:
            Combined synthesis string
        """
        lines = []

        for agent_name, output in outputs.items():
            if isinstance(output, dict):
                if "data" in output:
                    lines.append(f"From {agent_name}: {output['data']}")
                else:
                    lines.append(f"From {agent_name}: {output}")
            else:
                lines.append(f"From {agent_name}: {output}")

        return "\n".join(lines)

    def get_definition(self) -> ToolDefinition:
        """Get tool definition."""
        return ToolDefinition(
            name=self.name,
            description=self.description,
            parameters=[
                ToolParameter(
                    name="agent_outputs",
                    description="Outputs from different agents",
                    type="object",
                    required=True,
                ),
                ToolParameter(
                    name="original_query",
                    description="Original user query",
                    type="string",
                    required=True,
                ),
            ],
            category=self.category,
        )


class OrchestratorAgent(BaseAgent):
    """
    Orchestrator Agent - Central coordinator for multi-agent system.

    Provides tools for:
    - Analyzing queries
    - Managing conversations
    - Routing to agents
    - Synthesizing responses
    """

    name: str = "orchestrator"
    description: str = "Central coordinator for the multi-agent system"
    version = "1.0.0"

    def __init__(self):
        """Initialize orchestrator agent."""
        super().__init__()

        # Create tool instances
        analyze_tool = AnalyzeQueryTool()
        create_conv_tool = CreateConversationTool()
        get_conv_tool = GetConversationContextTool()
        add_msg_tool = AddConversationMessageTool()
        synthesize_tool = SynthesizeResponseTool()

        # Share conversation storage between tools
        self.conversations: Dict[str, ConversationContext] = {}
        create_conv_tool.conversations = self.conversations
        get_conv_tool.conversations = self.conversations
        add_msg_tool.conversations = self.conversations

        # Register tools
        self.register_tool(analyze_tool)
        self.register_tool(create_conv_tool)
        self.register_tool(get_conv_tool)
        self.register_tool(add_msg_tool)
        self.register_tool(synthesize_tool)

        logger.info("OrchestratorAgent initialized with 5 tools")

    async def initialize(self) -> None:
        """Initialize orchestrator agent resources."""
        logger.info("Orchestrator agent ready")

    async def stream(self, query: str):
        session_id = str(uuid4())

        # 1️⃣ Analyze query
        analysis = await self.execute_tool(
            "analyze_query",
            {"query": query, "session_id": session_id}
        )

        yield {
            "type": "analysis",
            "data": analysis.data,
        }

        # 🧭 Decide routing based on LLM analysis
        analysis_data = analysis.data or {}

        primary_agent = analysis_data.get("primary_agent")
        secondary_agents = set(analysis_data.get("secondary_agents", []))
        intent = analysis_data.get("intent")

        call_graph_agent = (
            primary_agent == "graph_query"
            or "graph_query" in secondary_agents
        )

        call_code_agent = (
            primary_agent == "code_analyst"
            or "code_analyst" in secondary_agents
            or intent in {"code_explanation", "dependency_analysis"}
        )


        agent_outputs = {}

        # 2️⃣ Call GraphQueryAgent (if required)
        if call_graph_agent:
            safe_graph_result = await self._safe_execute_agent(
                agent_name="graph_query",
                agent_callable=self.graph_query_agent.execute_tool,
                tool_name="search_entities",
                arguments={
                    "pattern": "FastAPI"
                },
            )

            if safe_graph_result["success"]:
                graph_result = safe_graph_result["data"]
                agent_outputs["graph_query"] = graph_result.data

                yield {
                    "type": "context",
                    "agent": "graph_query",
                    "data": graph_result.data,
                }
            else:
                yield {
                    "type": "warning",
                    "agent": "graph_query",
                    "error": safe_graph_result["error"],
                }

        # 3️⃣ Call CodeAnalystAgent (if required)
        if call_code_agent:
            # Try to extract a function or class name from LLM analysis
            entities = analysis_data.get("entities", {})
            function_names = entities.get("functions", [])
            class_names = entities.get("classes", [])

            if function_names:
                tool_name = "analyze_function"
                arguments = {"name": function_names[0]}
            elif class_names:
                tool_name = "analyze_class"
                arguments = {"name": class_names[0]}
            else:
                yield {
                    "type": "warning",
                    "agent": "code_analyst",
                    "error": "No specific function or class identified for code analysis",
                }
                tool_name = None

            if tool_name:
                safe_code_result = await self._safe_execute_agent(
                    agent_name="code_analyst",
                    agent_callable=self.code_analyst_agent.execute_tool,
                    tool_name=tool_name,
                    arguments=arguments,
                )

                if safe_code_result["success"]:
                    code_result = safe_code_result["data"]
                    agent_outputs["code_analyst"] = code_result.data

                    yield {
                        "type": "context",
                        "agent": "code_analyst",
                        "data": code_result.data,
                    }
                else:
                    yield {
                        "type": "warning",
                        "agent": "code_analyst",
                        "error": safe_code_result["error"],
                    }

        # 4️⃣ Fail gracefully if no agents succeeded
        if not agent_outputs:
            yield {
                "type": "final",
                "error": "No agents were able to process the request",
            }
            return

        # 5️⃣ Final synthesis
        synthesis = await self.execute_tool(
            "synthesize_response",
            {
                "agent_outputs": agent_outputs,
                "original_query": query,
            }
        )

        yield {
            "type": "final",
            "data": synthesis.data,
        }
    async def _safe_execute_agent(
        self,
        agent_name: str,
        agent_callable,
        *,
        tool_name: str,
        arguments: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Safely execute an agent tool and capture failures without breaking orchestration.
        """
        try:
            result = await agent_callable(tool_name, arguments)
            return {
                "success": True,
                "data": result,
                "error": None,
            }
        except Exception as e:
            logger.error(
                "Agent execution failed",
                agent=agent_name,
                tool=tool_name,
                error=str(e),
            )
            return {
                "success": False,
                "data": None,
                "error": str(e),
            }

    async def startup(self) -> None:
        """Start the orchestrator agent."""
        await super().startup()
        await self.initialize()
        logger.info("Orchestrator agent started")

    async def shutdown(self) -> None:
        """Shut down the orchestrator agent."""
        await super().shutdown()
        logger.info("Orchestrator agent shut down")
