"""
Gateway request/response models.

WHAT: Pydantic models for API requests and responses
WHY: Type safety and validation for all endpoints
HOW: Define models for each endpoint group
"""

from typing import Optional
from pydantic import BaseModel


# ========================
# Chat Models
# ========================

class ChatRequest(BaseModel):
    """Chat request model."""

    query: str
    """User query"""

    session_id: Optional[str] = None
    """Optional session ID"""


class ChatResponse(BaseModel):
    """Chat response model."""

    session_id: str
    """Session ID"""

    response: str
    """Response text"""

    agents_used: list
    """Agents that were used"""

    correlation_id: str
    """Correlation ID for tracing"""


# ========================
# Indexing Models
# ========================

class IndexRequest(BaseModel):
    """Repository indexing request."""

    repo_url: str
    """Repository URL"""

    full_index: bool = True
    """Whether to do full index"""


class IndexResponse(BaseModel):
    """Repository indexing response."""

    status: str
    """Indexing status"""

    files_processed: int
    """Number of files processed"""

    entities_created: int
    """Number of entities created"""

    relationships_created: int
    """Number of relationships created"""


class IndexJobResponse(BaseModel):
    """Index job response (for async indexing)."""

    job_id: str
    """Unique job ID"""

    status: str
    """Job status: pending, running, completed, failed"""

    repo_url: str
    """Repository URL"""

    created_at: str
    """When job was created"""

    correlation_id: str
    """Correlation ID for tracing"""


class IndexJobStatusResponse(BaseModel):
    """Index job status response."""

    job_id: str
    """Job ID"""

    status: str
    """Job status"""

    progress: Optional[float] = None
    """Progress percentage (0-100)"""

    files_processed: Optional[int] = None
    """Files processed so far"""

    entities_created: Optional[int] = None
    """Entities created so far"""

    relationships_created: Optional[int] = None
    """Relationships created so far"""

    error: Optional[str] = None
    """Error message if failed"""

    correlation_id: str
    """Correlation ID for tracing"""
