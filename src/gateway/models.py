"""
Gateway request/response models.

WHAT: Pydantic models for API requests and responses
WHY: Type safety and validation for all endpoints
HOW: Define models for each endpoint group
"""

from typing import Optional, List
from pydantic import BaseModel


# ========================
# Chat Models
# ========================

class ChatRequest(BaseModel):
    """Chat request model from Streamlit/clients."""

    query: str
    """User query to process"""

    session_id: Optional[str] = None
    """Optional session ID for conversation context"""
    
    class Config:
        """Pydantic config."""
        json_schema_extra = {
            "example": {
                "query": "What is the FastAPI class?",
                "session_id": "550e8400-e29b-41d4-a716-446655440000"
            }
        }


class ChatResponse(BaseModel):
    """Response from Orchestrator to client."""
    
    success: bool
    """Whether query was processed successfully"""
    
    response: str
    """Final synthesized response from agents"""
    
    agents_used: List[str]
    """List of agents that processed the query"""
    
    intent: Optional[str] = None
    """Detected query intent"""
    
    entities_found: List[str] = []
    """Entities extracted from query"""
    
    session_id: Optional[str] = None
    """Session ID for this conversation"""
    
    error: Optional[str] = None
    """Error message if unsuccessful"""
    
    class Config:
        """Pydantic config."""
        json_schema_extra = {
            "example": {
                "success": True,
                "response": "FastAPI is a modern web framework...",
                "agents_used": ["graph_query", "code_analyst"],
                "intent": "explain",
                "entities_found": ["FastAPI"],
                "session_id": "550e8400-e29b-41d4-a716-446655440000"
            }
        }


# ========================
# Indexing Models
# ========================

class IndexRequest(BaseModel):
    """Repository indexing request."""

    repo_url: str
    """Repository URL to index"""

    branch: str = "main"
    """Git branch to index"""


class IndexResponse(BaseModel):
    """Repository indexing response."""

    status: str
    """Indexing status: pending, running, completed, failed"""

    files_processed: int
    """Number of files processed"""

    entities_created: int
    """Number of entities created"""

    relationships_created: int
    """Number of relationships created"""


class IndexStatusResponse(BaseModel):
    """Index status response."""

    status: str
    """Current indexing status"""

    progress: Optional[float] = None
    """Progress percentage (0-100)"""

    files_processed: Optional[int] = None
    """Files processed so far"""

    entities_created: Optional[int] = None
    """Entities created so far"""

    error: Optional[str] = None
    """Error message if failed"""