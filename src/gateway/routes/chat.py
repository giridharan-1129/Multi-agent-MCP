"""
Chat endpoint - Now unified with RAG (uses both embeddings + graph).

DEPRECATED: Use /api/rag-chat instead for full context retrieval.
This endpoint kept for backward compatibility.
"""

from fastapi import APIRouter, HTTPException
from ...shared.logger import (
    get_logger,
    generate_correlation_id,
    set_correlation_id,
)
from ..models import ChatRequest, ChatResponse
from ..dependencies import get_orchestrator

logger = get_logger(__name__)
router = APIRouter(tags=["chat"])


@router.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest):
    """
    ⚠️ DEPRECATED: Use /api/rag-chat instead.
    
    This endpoint now delegates to RAG chat for consistency.
    Retrieves context from BOTH embeddings and knowledge graph.
    """
    correlation_id = generate_correlation_id()
    set_correlation_id(correlation_id)

    logger.info(
        "Chat request received (legacy endpoint)",
        query=request.query[:200],
        session_id=request.session_id,
    )

    try:
        # Import RAG chat logic
        from .rag_chat import rag_chat as rag_handler
        from .rag_chat import RAGChatRequest
        
        # Convert to RAG request
        rag_request = RAGChatRequest(
            query=request.query,
            session_id=request.session_id,
            retrieve_limit=5
        )
        
        # Call RAG handler
        rag_response = await rag_handler(rag_request)
        
        # Convert RAG response to Chat response
        return ChatResponse(
            session_id=rag_response.session_id,
            response=rag_response.response,
            agents_used=rag_response.agents_used,
            correlation_id=correlation_id,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Chat request failed",
            error=str(e),
            correlation_id=correlation_id,
        )
        raise HTTPException(status_code=500, detail=str(e))