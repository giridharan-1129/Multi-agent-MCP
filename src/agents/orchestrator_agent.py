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

    name = "analyze_query"
    description = "Analyze a user query to determine intent and required agents"
    category = "orchestration"

    async def execute(
        self,
        query: str,
        session_id: Optional[str] = None,
    ) -> ToolResult:
        """
        Analyze a query.

        Args:
            query: User query
            session_id: Optional session ID for context

        Returns:
            ToolResult with query analysis
        """
        try:
            # Determine intent based on keywords
            query_lower = query.lower()

            intent = "general"
            if any(word in query_lower for word in ["import", "depend", "relation"]):
                intent = "dependency_analysis"
            elif any(word in query_lower for word in ["how", "work", "explain"]):
                intent = "explanation"
            elif any(word in query_lower for word in ["find", "search", "show", "list"]):
                intent = "search"
            elif any(word in query_lower for word in ["pattern", "design", "architecture"]):
                intent = "pattern_analysis"
            elif any(word in query_lower for word in ["compare", "difference", "vs"]):
                intent = "comparison"

            # Extract entities (basic keyword extraction)
            entities = []
            keywords = [
                "FastAPI", "APIRouter", "Depends", "Request", "Response",
                "HTTPException", "Starlette", "Pydantic", "openapi",
                "decorator", "middleware", "route", "endpoint",
            ]
            for keyword in keywords:
                if keyword.lower() in query_lower:
                    entities.append(keyword)

            # Determine which agents to use
            required_agents = ["graph_query"]  # Always use graph query

            if intent in ["explanation", "pattern_analysis", "comparison"]:
                required_agents.append("code_analyst")

            if intent == "dependency_analysis":
                required_agents.extend(["graph_query", "code_analyst"])

            if "index" in query_lower or "repository" in query_lower:
                required_agents.append("indexer")

            analysis = QueryAnalysis(
                query=query,
                intent=intent,
                entities=entities,
                required_agents=list(set(required_agents)),
                context_needed=session_id is not None,
                follow_up=False,
                confidence=0.8,
            )

            logger.info(
                "Query analyzed",
                intent=intent,
                agents=analysis.required_agents,
                entities=len(entities),
            )

            return ToolResult(
                success=True,
                data=analysis.dict(),
            )

        except Exception as e:
            logger.error("Failed to analyze query", error=str(e))
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

    name = "create_conversation"
    description = "Create a new conversation session"
    category = "orchestration"

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

    name = "get_conversation_context"
    description = "Get conversation history and context"
    category = "orchestration"

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

    name = "add_conversation_message"
    description = "Add a message to the conversation history"
    category = "orchestration"

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

    name = "synthesize_response"
    description = "Combine outputs from multiple agents into a coherent response"
    category = "orchestration"

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

    name = "orchestrator"
    description = "Central coordinator for the multi-agent system"
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

    async def startup(self) -> None:
        """Start the orchestrator agent."""
        await super().startup()
        await self.initialize()
        logger.info("Orchestrator agent started")

    async def shutdown(self) -> None:
        """Shut down the orchestrator agent."""
        await super().shutdown()
        logger.info("Orchestrator agent shut down")
