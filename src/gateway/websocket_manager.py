from typing import Dict
from fastapi import WebSocket
import uuid
import logging

logger = logging.getLogger(__name__)


class ConnectionManager:
    """
    Manages WebSocket connections and per-session state.
    """

    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}

    def set_orchestrator(self, orchestrator):
        self.orchestrator = orchestrator


    async def connect(self, websocket: WebSocket) -> str:
        await websocket.accept()
        session_id = str(uuid.uuid4())
        self.active_connections[session_id] = websocket
        logger.info("WebSocket connected", extra={"session_id": session_id})
        return session_id

    def disconnect(self, session_id: str):
        self.active_connections.pop(session_id, None)
        logger.info("WebSocket disconnected", extra={"session_id": session_id})

    async def send_text(self, session_id: str, message: str):
        websocket = self.active_connections.get(session_id)
        if websocket:
            await websocket.send_text(message)

    async def send_json(self, session_id: str, data: dict):
        websocket = self.active_connections.get(session_id)
        if websocket:
            await websocket.send_json(data)
            
    async def handle_query(self, websocket, query_text: str):
        """
        Handle WebSocket query with unified RAG (embeddings + graph).
        Streams real-time results to client.
        """
        session_id = str(uuid.uuid4())

        await websocket.send_json({
            "type": "session_started",
            "session_id": session_id,
            "message": f"Processing: {query_text}"
        })

        try:
            # Import RAG function
            from ..routes.rag_chat import rag_chat
            from ..routes.rag_chat import RAGChatRequest
            
            # Create RAG request
            rag_request = RAGChatRequest(
                query=query_text,
                session_id=session_id,
                retrieve_limit=5
            )
            
            # Stream progress events
            await websocket.send_json({
                "type": "searching",
                "status": "Searching embeddings and graph..."
            })
            
            # Execute RAG handler
            rag_response = await rag_chat(rag_request)
            
            # Send context found
            await websocket.send_json({
                "type": "context_found",
                "embeddings_count": len([c for c in rag_response.retrieved_context if c.get('type') == 'code_chunk']),
                "relationships_count": len([c for c in rag_response.retrieved_context if c.get('type') == 'relationship']),
                "context": rag_response.retrieved_context
            })
            
            # Send response
            await websocket.send_json({
                "type": "response",
                "message": rag_response.response,
                "agents_used": rag_response.agents_used,
                "session_id": rag_response.session_id
            })
            
            # Mark complete
            await websocket.send_json({
                "type": "complete",
                "correlation_id": rag_response.correlation_id
            })

        except Exception as e:
            logger.exception("WebSocket query handling failed")
            await websocket.send_json({
                "type": "error",
                "message": f"Query processing failed: {str(e)}"
            })

# Singleton instance
ws_manager = ConnectionManager()
