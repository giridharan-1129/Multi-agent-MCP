from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from ..websocket_manager import ws_manager
import logging
import json
from pydantic import BaseModel

router = APIRouter()
logger = logging.getLogger(__name__)

class WSQuery(BaseModel):
    type: str
    text: str
    
@router.websocket("/ws/chat")
async def websocket_chat(websocket: WebSocket):
    session_id = await ws_manager.connect(websocket)

    try:
        while True:
            raw = await websocket.receive_text()
            payload = json.loads(raw)

            if payload.get("type") == "query":
                await ws_manager.handle_query(
                    websocket=websocket,
                    query_text=payload["text"],
                )

    except WebSocketDisconnect:
        ws_manager.disconnect(session_id)

    except Exception:
        logger.exception("WebSocket error")
        ws_manager.disconnect(session_id)
