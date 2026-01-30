"""
Chat endpoint.

WHAT: POST /api/chat endpoint
WHY: REST API for synchronous chat interactions
HOW: Route to orchestrator, analyze query, synthesize response
"""

from fastapi import APIRouter, HTTPException

from ...shared.logger import get_logger, generate_correlation_id, set_correlation_id
from ..models import ChatRequest, ChatResponse
from ..dependencies import get_orchestrator

logger = get_logger(__name__)
router = APIRouter(tags=["chat"])


@router.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    Chat with the system.

    Args:
        request: Chat request with query and optional session_id

    Returns:
        Chat response with answer and session info
    """
    correlation_id = generate_correlation_id()
    set_correlation_id(correlation_id)

    try:
        orchestrator = get_orchestrator()

        logger.info(
            "Chat request received",
            query=request.query[:100],
            session_id=request.session_id,
        )

        # Create or get session
        session_id = request.session_id
        if not session_id:
            # Create new session
            create_result = await orchestrator.execute_tool(
                "create_conversation",
                {},
            )
            if create_result.success:
                session_id = create_result.data.get("session_id")
            else:
                raise HTTPException(status_code=500, detail="Failed to create session")

        # Analyze query
        analysis_result = await orchestrator.execute_tool(
            "analyze_query",
            {
                "query": request.query,
                "session_id": session_id,
            },
        )

        if not analysis_result.success:
            raise HTTPException(status_code=400, detail="Query analysis failed")

        analysis = analysis_result.data
        agents_used = analysis.get("required_agents", ["orchestrator"])

        # Add user message to conversation
        await orchestrator.execute_tool(
            "add_conversation_message",
            {
                "session_id": session_id,
                "role": "user",
                "content": request.query,
            },
        )

        # For now, create a simple response
        # In a full implementation, would call other agents based on analysis
        response_text = f"I analyzed your query about {', '.join(analysis.get('entities', ['code']))}. "
        response_text += f"This appears to be a {analysis.get('intent', 'general')} question. "
        response_text += f"I would route this to: {', '.join(agents_used)}."

        # Add assistant message to conversation
        await orchestrator.execute_tool(
            "add_conversation_message",
            {
                "session_id": session_id,
                "role": "assistant",
                "content": response_text,
                "agent_name": "orchestrator",
            },
        )

        logger.info(
            "Chat response generated",
            session_id=session_id,
            agents=len(agents_used),
        )

        return ChatResponse(
            session_id=session_id,
            response=response_text,
            agents_used=agents_used,
            correlation_id=correlation_id,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Chat request failed", error=str(e), correlation_id=correlation_id)
        raise HTTPException(status_code=500, detail=str(e))
