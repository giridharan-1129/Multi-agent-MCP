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
        session_id = str(uuid.uuid4())

        await websocket.send_json({
            "type": "ack",
            "session_id": session_id,
            "message": query_text
        })

        try:
            async for event in self.orchestrator.stream(query_text):
                await websocket.send_json(event)

        except Exception as e:
            await websocket.send_json({
                "type": "error",
                "message": str(e)
            })


# Singleton instance
ws_manager = ConnectionManager()
