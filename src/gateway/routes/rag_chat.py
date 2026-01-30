"""
RAG (Retrieval-Augmented Generation) Chat endpoint.

Retrieves relevant context from knowledge graph before generating responses.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ...shared.logger import get_logger, generate_correlation_id, set_correlation_id
from ...shared.neo4j_service import get_neo4j_service
from ..dependencies import get_orchestrator

logger = get_logger(__name__)
router = APIRouter(tags=["rag_chat"], prefix="/api")


class RAGChatRequest(BaseModel):
    """RAG chat request."""
    query: str
    session_id: str = None
    retrieve_limit: int = 5


class RAGChatResponse(BaseModel):
    """RAG chat response with retrieved context."""
    session_id: str
    response: str
    retrieved_context: list
    agents_used: list
    correlation_id: str


@router.post("/rag-chat", response_model=RAGChatResponse)
async def rag_chat(request: RAGChatRequest):
    """
    RAG-enhanced chat endpoint.
    
    Retrieves relevant entities from knowledge graph before generating response.
    
    Args:
        request: RAG chat request with query and optional session_id
    
    Returns:
        RAG chat response with retrieved context and response
    """
    correlation_id = generate_correlation_id()
    set_correlation_id(correlation_id)
    
    try:
        orchestrator = get_orchestrator()
        neo4j = get_neo4j_service()
        
        logger.info(
            "RAG chat request received",
            query=request.query[:100],
            session_id=request.session_id,
        )
        
        # Step 1: Retrieve relevant context from knowledge graph
        logger.info("Retrieving context from knowledge graph", query=request.query)
        retrieved_entities = await neo4j.search_entities(
            request.query, 
            limit=request.retrieve_limit
        )
        
        logger.info("Entities retrieved", count=len(retrieved_entities))
        
        # Step 2: Create or get session
        session_id = request.session_id
        if not session_id:
            create_result = await orchestrator.execute_tool(
                "create_conversation",
                {},
            )
            if create_result.success:
                session_id = create_result.data.get("session_id")
            else:
                raise HTTPException(status_code=500, detail="Failed to create session")
        
        # Step 3: Analyze query
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
        
        # Step 4: Add user message to conversation
        await orchestrator.execute_tool(
            "add_conversation_message",
            {
                "session_id": session_id,
                "role": "user",
                "content": request.query,
            },
        )
        
        # Step 5: Build augmented response with retrieved context
        context_text = ""
        if retrieved_entities:
            context_text = "\n\nRetrieved Context from Knowledge Graph:\n"
            for i, entity in enumerate(retrieved_entities, 1):
                context_text += f"\n{i}. {entity.get('type', 'Unknown')}: {entity.get('name', 'Unknown')}"
                if entity.get('docstring'):
                    context_text += f"\n   Documentation: {entity['docstring'][:200]}..."
                if entity.get('module'):
                    context_text += f"\n   Location: {entity['module']}"
        
        # Step 6: Generate response
        response_text = f"I analyzed your query about {', '.join(analysis.get('entities', ['code']))}."
        response_text += f"\n\nThis appears to be a {analysis.get('intent', 'general')} question."
        response_text += f"\n\nI would route this to: {', '.join(agents_used)}."
        
        if retrieved_entities:
            response_text += context_text
        
        # Step 7: Add assistant message to conversation
        await orchestrator.execute_tool(
            "add_conversation_message",
            {
                "session_id": session_id,
                "role": "assistant",
                "content": response_text,
                "agent_name": "rag_orchestrator",
            },
        )
        
        logger.info(
            "RAG chat response generated",
            session_id=session_id,
            entities_retrieved=len(retrieved_entities),
            agents=len(agents_used),
        )
        
        return RAGChatResponse(
            session_id=session_id,
            response=response_text,
            retrieved_context=retrieved_entities,
            agents_used=agents_used,
            correlation_id=correlation_id,
        )
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error("RAG chat request failed", error=str(e), correlation_id=correlation_id)
        raise HTTPException(status_code=500, detail=str(e))
