"""
WebSocket chat endpoint.

WHAT: WS /ws/chat endpoint
WHY: Real-time streaming chat interactions
HOW: Accept WebSocket, stream responses as they're generated
"""

import json
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ...shared.logger import get_logger, generate_correlation_id, set_correlation_id
from ..dependencies import get_orchestrator

logger = get_logger(__name__)
router = APIRouter(tags=["websocket"])


@router.websocket("/ws/chat")
async def websocket_chat(websocket: WebSocket):
    """
    WebSocket endpoint for real-time chat.
    
    Accepts WebSocket connections and streams responses.
    Message format: {"query": "...", "session_id": "..."}
    
    Args:
        websocket: WebSocket connection
    """
    correlation_id = generate_correlation_id()
    set_correlation_id(correlation_id)
    
    await websocket.accept()
    session_id = None
    
    try:
        logger.info(
            "WebSocket connection established",
            correlation_id=correlation_id,
        )
        
        while True:
            # Receive message from client
            data = await websocket.receive_text()
            
            try:
                message = json.loads(data)
            except json.JSONDecodeError:
                await websocket.send_json({
                    "error": "Invalid JSON",
                    "correlation_id": correlation_id,
                })
                continue
            
            query = message.get("query")
            session_id = message.get("session_id")
            
            if not query:
                await websocket.send_json({
                    "error": "query is required",
                    "correlation_id": correlation_id,
                })
                continue
            
            logger.info(
                "WebSocket message received",
                query=query[:100],
                session_id=session_id,
                correlation_id=correlation_id,
            )
            
            try:
                orchestrator = get_orchestrator()
                
                # Create or get session
                if not session_id:
                    create_result = await orchestrator.execute_tool(
                        "create_conversation",
                        {},
                    )
                    if create_result.success:
                        session_id = create_result.data.get("session_id")
                        await websocket.send_json({
                            "type": "session_created",
                            "session_id": session_id,
                            "correlation_id": correlation_id,
                        })
                    else:
                        await websocket.send_json({
                            "error": "Failed to create session",
                            "correlation_id": correlation_id,
                        })
                        continue
                
                # Send thinking indicator
                await websocket.send_json({
                    "type": "thinking",
                    "message": "Analyzing query...",
                    "correlation_id": correlation_id,
                })
                
                # Analyze query
                analysis_result = await orchestrator.execute_tool(
                    "analyze_query",
                    {
                        "query": query,
                        "session_id": session_id,
                    },
                )
                
                if not analysis_result.success:
                    await websocket.send_json({
                        "error": "Query analysis failed",
                        "correlation_id": correlation_id,
                    })
                    continue
                
                analysis = analysis_result.data
                agents_used = analysis.get("required_agents", ["orchestrator"])
                
                # Send analysis info
                await websocket.send_json({
                    "type": "analysis",
                    "intent": analysis.get("intent"),
                    "entities": analysis.get("entities", []),
                    "agents_to_use": agents_used,
                    "correlation_id": correlation_id,
                })
                
                # Add user message to conversation
                await orchestrator.execute_tool(
                    "add_conversation_message",
                    {
                        "session_id": session_id,
                        "role": "user",
                        "content": query,
                    },
                )
                
                # Generate response
                response_text = f"I analyzed your query about {', '.join(analysis.get('entities', ['code']))}. "
                response_text += f"This appears to be a {analysis.get('intent', 'general')} question. "
                response_text += f"I would route this to: {', '.join(agents_used)}."
                
                # Stream response in chunks (simulate streaming)
                chunk_size = 50
                for i in range(0, len(response_text), chunk_size):
                    chunk = response_text[i:i+chunk_size]
                    await websocket.send_json({
                        "type": "response_chunk",
                        "chunk": chunk,
                        "correlation_id": correlation_id,
                    })
                
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
                
                # Send completion message
                await websocket.send_json({
                    "type": "response_complete",
                    "session_id": session_id,
                    "agents_used": agents_used,
                    "correlation_id": correlation_id,
                })
                
                logger.info(
                    "WebSocket response sent",
                    session_id=session_id,
                    agents=len(agents_used),
                    correlation_id=correlation_id,
                )
                
            except Exception as e:
                logger.error(
                    "Error processing WebSocket message",
                    error=str(e),
                    correlation_id=correlation_id,
                )
                await websocket.send_json({
                    "error": f"Error processing message: {str(e)}",
                    "correlation_id": correlation_id,
                })
    
    except WebSocketDisconnect:
        logger.info(
            "WebSocket connection closed",
            session_id=session_id,
            correlation_id=correlation_id,
        )
    except Exception as e:
        logger.error(
            "WebSocket error",
            error=str(e),
            correlation_id=correlation_id,
        )
        try:
            await websocket.send_json({
                "error": f"WebSocket error: {str(e)}",
                "correlation_id": correlation_id,
            })
        except:
            pass
        await websocket.close(code=1011)
