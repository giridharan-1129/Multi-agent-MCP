"""
Repository indexing endpoints with job tracking.

WHAT: /api/index endpoints with async job support
WHY: Non-blocking indexing with progress tracking
HOW: Return job_id immediately, track progress asynchronously
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

# In-memory job tracking (use Redis/database in production)
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
        "relationships_created": 0,
        "error": None,
    }
    logger.info("Job created", job_id=job_id, repo_url=repo_url)
    return job_id


async def _background_index_task(job_id: str, repo_url: str) -> None:
    """Background task for indexing repository."""
    try:
        indexer = get_indexer()
        job = index_jobs[job_id]
        
        # Update status to running
        job["status"] = "running"
        logger.info("Index job started", job_id=job_id)
        
        # Execute indexing
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
            job["relationships_created"] = data.get("relationships_created", 0)
            logger.info(
                "Index job completed",
                job_id=job_id,
                entities=data.get("entities_created"),
            )
        else:
            job["status"] = "failed"
            job["error"] = result.error
            logger.error(
                "Index job failed",
                job_id=job_id,
                error=result.error,
            )
            
    except Exception as e:
        job = index_jobs.get(job_id)
        if job:
            job["status"] = "failed"
            job["error"] = str(e)
        logger.error("Index job exception", job_id=job_id, error=str(e))


@router.post("/api/index", response_model=IndexJobResponse)
async def index_repository(request: IndexRequest, background_tasks: BackgroundTasks):
    """
    Start repository indexing job (asynchronous).

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
            "Index request received",
            repo_url=request.repo_url,
        )

        # Create job
        job_id = _create_job(request.repo_url, correlation_id)
        
        # Start background task
        background_tasks.add_task(_background_index_task, job_id, request.repo_url)

        return IndexJobResponse(
            job_id=job_id,
            status="pending",
            repo_url=request.repo_url,
            created_at=index_jobs[job_id]["created_at"],
            correlation_id=correlation_id,
        )

    except Exception as e:
        logger.error("Index request failed", error=str(e), correlation_id=correlation_id)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/index/jobs/{job_id}", response_model=IndexJobStatusResponse)
async def get_index_job_status(job_id: str):
    """
    Get status of an indexing job.

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

        logger.info("Job status retrieved", job_id=job_id, status=job["status"])

        return IndexJobStatusResponse(
            job_id=job_id,
            status=job["status"],
            progress=job.get("progress"),
            files_processed=job.get("files_processed"),
            entities_created=job.get("entities_created"),
            relationships_created=job.get("relationships_created"),
            error=job.get("error"),
            correlation_id=correlation_id,
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get job status", error=str(e), job_id=job_id)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/api/index/status")
async def get_index_summary():
    """
    Get knowledge graph statistics (current state).

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

        logger.info("Index status retrieved")
        return {
            "status": "ok",
            "statistics": result.data,
            "correlation_id": correlation_id,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get index status", error=str(e))
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

        logger.info("Jobs listed", count=len(jobs), status_filter=status)

        return {
            "jobs": jobs,
            "count": len(jobs),
            "correlation_id": correlation_id,
        }

    except Exception as e:
        logger.error("Failed to list jobs", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))
