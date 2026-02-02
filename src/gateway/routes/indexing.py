"""
Repository indexing endpoints - showcases Indexer Agent capabilities.

Endpoints for triggering and monitoring repository indexing into Neo4j.
"""

import uuid
from datetime import datetime
from typing import Dict, Optional
from fastapi import APIRouter, HTTPException, BackgroundTasks

from ...shared.logger import get_logger, generate_correlation_id, set_correlation_id
from ..models import IndexRequest, IndexJobResponse, IndexJobStatusResponse
from ..dependencies import get_indexer

logger = get_logger(__name__)
router = APIRouter(tags=["indexing"])

# In-memory job tracking
index_jobs: Dict[str, dict] = {}


def _create_job(repo_url: str, correlation_id: str) -> str:
    """Create a new indexing job."""
    job_id = str(uuid.uuid4())
    index_jobs[job_id] = {
        "id": job_id,
        "status": "pending",
        "repo_url": repo_url,
        "created_at": datetime.utcnow().isoformat(),
        "correlation_id": correlation_id,
        "progress": 0,
        "files_processed": 0,
        "entities_created": 0,
        "packages_created": 0,
        "relationships_created": 0,
        "error": None,
    }
    logger.info(f"📋 Job created", job_id=job_id, repo_url=repo_url)
    return job_id


async def _background_index_task(job_id: str, repo_url: str) -> None:
    """
    Background task that executes Indexer Agent's index_repository tool.
    
    This showcases the Indexer Agent in action.
    """
    try:
        indexer = get_indexer()
        job = index_jobs[job_id]
        
        # Update status to running
        job["status"] = "running"
        logger.info(f"🚀 Index job started: {job_id}")
        
        # Call Indexer Agent's index_repository tool
        logger.info(f"Calling Indexer Agent: index_repository('{repo_url}')")
        result = await indexer.execute_tool(
            "index_repository",
            {
                "repo_url": repo_url,
                "full_index": True,
            },
        )
        
        if result.success:
            data = result.data
            job["status"] = "completed"
            job["progress"] = 100
            job["files_processed"] = data.get("files_processed", 0)
            job["entities_created"] = data.get("entities_created", 0)
            job["packages_created"] = data.get("packages_created", 0)
            job["relationships_created"] = data.get("relationships_created", 0)
            logger.info(
                f"✅ Index job completed",
                job_id=job_id,
                files=data.get("files_processed"),
                entities=data.get("entities_created"),
            )
        else:
            job["status"] = "failed"
            job["error"] = result.error
            logger.error(
                f"❌ Index job failed",
                job_id=job_id,
                error=result.error,
            )
            
    except Exception as e:
        job = index_jobs.get(job_id)
        if job:
            job["status"] = "failed"
            job["error"] = str(e)
        logger.error(f"❌ Index job exception: {str(e)}", job_id=job_id)


@router.post("/api/index", response_model=IndexJobResponse)
async def index_repository(request: IndexRequest, background_tasks: BackgroundTasks):
    """
    Start repository indexing job (asynchronous).
    
    Triggers the Indexer Agent to:
    1. Clone repository from GitHub
    2. Parse Python files using AST
    3. Extract entities (Classes, Functions, etc.)
    4. Build relationships (Imports, Inheritance, Calls)
    5. Populate Neo4j knowledge graph

    Args:
        request: Indexing request with repo URL
        background_tasks: FastAPI background tasks

    Returns:
        Job info with job_id for tracking
    """
    correlation_id = generate_correlation_id()
    set_correlation_id(correlation_id)

    try:
        logger.info(
            f"📋 Index request received",
            repo_url=request.repo_url,
        )

        # Validate and sanitize repo URL
        if not request.repo_url.startswith(('http://', 'https://')):
            raise HTTPException(status_code=400, detail="repo_url must be a valid HTTP(S) URL")

        # SANITIZE: Remove duplicate path segments
        # e.g., https://github.com/tiangolo/fastapi/fastapi -> https://github.com/tiangolo/fastapi
        repo_url = request.repo_url.rstrip('/')
        parts = repo_url.split('/')
        if len(parts) > 5 and parts[-1] == parts[-2]:  # Duplicate repo name
            repo_url = '/'.join(parts[:-1])
            logger.info(f"Sanitized duplicate path", original=request.repo_url, sanitized=repo_url)

        request.repo_url = repo_url

        # Create job
        job_id = _create_job(request.repo_url, correlation_id)
        
        # Start background indexing task
        background_tasks.add_task(_background_index_task, job_id, request.repo_url)

        logger.info(f"✅ Indexing job queued", job_id=job_id)

        return IndexJobResponse(
            job_id=job_id,
            status="pending",
            repo_url=request.repo_url,
            created_at=index_jobs[job_id]["created_at"],
            correlation_id=correlation_id,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Index request failed: {str(e)}", correlation_id=correlation_id)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/index/jobs/{job_id}", response_model=IndexJobStatusResponse)
async def get_index_job_status(job_id: str):
    """
    Get status of an indexing job.

    Tracks progress through:
    - pending: Waiting to start
    - running: Currently indexing
    - completed: Successfully finished
    - failed: Indexing failed

    Args:
        job_id: Job ID from initial indexing request

    Returns:
        Job status with progress and statistics
    """
    correlation_id = generate_correlation_id()
    set_correlation_id(correlation_id)

    try:
        if job_id not in index_jobs:
            raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

        job = index_jobs[job_id]

        logger.info(f"📊 Job status retrieved", job_id=job_id, status=job["status"])

        return IndexJobStatusResponse(
            job_id=job_id,
            status=job["status"],
            progress=job.get("progress"),
            files_processed=job.get("files_processed"),
            entities_created=job.get("entities_created"),
            packages_created=job.get("packages_created"),
            relationships_created=job.get("relationships_created"),
            error=job.get("error"),
            correlation_id=correlation_id,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Failed to get job status: {str(e)}", job_id=job_id)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/index/jobs")
async def list_index_jobs(status: Optional[str] = None):
    """
    List all indexing jobs (optionally filtered by status).

    Args:
        status: Filter by status (pending, running, completed, failed)

    Returns:
        List of jobs
    """
    correlation_id = generate_correlation_id()
    set_correlation_id(correlation_id)

    try:
        jobs = list(index_jobs.values())
        
        # Filter by status if provided
        if status:
            jobs = [j for j in jobs if j["status"] == status]

        logger.info(f"📋 Jobs listed", count=len(jobs), status_filter=status)

        return {
            "jobs": jobs,
            "count": len(jobs),
            "correlation_id": correlation_id,
        }

    except Exception as e:
        logger.error(f"❌ Failed to list jobs: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/index/status")
async def get_index_summary():
    """
    Get knowledge graph statistics (current state).
    
    Shows the result of all indexing operations:
    - Total nodes by type (Package, Class, Function, etc.)
    - Total relationships by type (CONTAINS, INHERITS_FROM, CALLS, etc.)
    - Summary statistics

    Returns:
        Graph statistics
    """
    correlation_id = generate_correlation_id()
    set_correlation_id(correlation_id)

    try:
        indexer = get_indexer()
        result = await indexer.execute_tool("get_index_status", {})

        if not result.success:
            raise HTTPException(status_code=400, detail=result.error)

        logger.info(f"📊 Index status retrieved")
        return {
            "status": "ok",
            "statistics": result.data,
            "correlation_id": correlation_id,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"❌ Failed to get index status: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))