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
        # 🔁 Execute orchestrator stream
        final_response = None

        async for event in orchestrator.stream(request.query):
            if event["type"] == "final":
                if "data" in event:
                    final_response = event["data"].get("synthesis")
                elif "error" in event:
                    raise HTTPException(status_code=500, detail=event["error"])

        if not final_response:
            raise HTTPException(status_code=500, detail="No response generated")

        # Add assistant message to conversation
        await orchestrator.execute_tool(
            "add_conversation_message",
            {
                "session_id": session_id,
                "role": "assistant",
                "content": final_response,
                "agent_name": "orchestrator",
            },
        )

        return ChatResponse(
            session_id=session_id,
            response=final_response,
            agents_used=["orchestrator"],
            correlation_id=correlation_id,
        )


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
