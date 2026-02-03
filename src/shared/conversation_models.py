"""
Conversation data models for memory and state management.

Pydantic models for:
- Conversation sessions
- Turns (user/assistant exchanges)
- Agent responses
- Conversation context
"""

from datetime import datetime
from typing import Any, Dict, List, Optional
from uuid import UUID
from pydantic import BaseModel, Field


class ConversationSession(BaseModel):
    """Represents a conversation session."""
    id: Optional[UUID] = None
    user_id: str
    session_name: Optional[str] = None
    created_at: Optional[datetime] = None
    closed_at: Optional[datetime] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    
    class Config:
        json_encoders = {UUID: str, datetime: str}


class ConversationTurn(BaseModel):
    """Represents a single turn (user or assistant message)."""
    id: Optional[UUID] = None
    session_id: UUID
    turn_number: int
    role: str  # "user" or "assistant"
    content: str
    turn_meta: Dict[str, Any] = Field(default_factory=dict)
    created_at: Optional[datetime] = None
    
    class Config:
        json_encoders = {UUID: str, datetime: str}


class AgentResponse(BaseModel):
    """Represents an agent's response to a turn."""
    id: Optional[UUID] = None
    turn_id: UUID
    agent_name: str
    tools_used: List[str] = Field(default_factory=list)
    result: str
    duration_ms: Optional[int] = None
    created_at: Optional[datetime] = None
    
    class Config:
        json_encoders = {UUID: str, datetime: str}


class ConversationContext(BaseModel):
    """Current conversation context for agents."""
    session_id: UUID
    current_turn_number: int
    user_message: str
    previous_turns: List[ConversationTurn] = Field(default_factory=list)
    last_agents_used: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)
    
    class Config:
        json_encoders = {UUID: str}


class MemoryQuery(BaseModel):
    """Query for retrieving conversation memory."""
    session_id: UUID
    limit: int = 10
    include_metadata: bool = True


class MemoryStore(BaseModel):
    """Request to store conversation turn."""
    session_id: UUID
    role: str
    content: str
    metadata: Dict[str, Any] = Field(default_factory=dict)


class AgentResponseStore(BaseModel):
    """Request to store agent response."""
    turn_id: UUID
    agent_name: str
    tools_used: List[str]
    result: str
    duration_ms: Optional[int] = None