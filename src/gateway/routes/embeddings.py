"""
Embeddings Route - FastAPI endpoints for Pinecone vector indexing.

Handles:
- Code splitting into 650-line chunks
- Embedding with semantic model
- Pinecone storage with metadata
- Cohere reranking pipeline
"""

from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import os
import logging
import asyncio
from pathlib import Path

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/embeddings", tags=["embeddings"])


class EmbedRequest(BaseModel):
    """Embedding request model."""
    repo_url: str
    """GitHub repository URL"""
    
    chunk_size: int = 650
    """Lines per chunk (default 650)"""


class SearchRequest(BaseModel):
    """Semantic search request."""
    repo_id: str
    """Repository ID"""
    
    query: str
    """Search query"""
    
    top_k: int = 10
    """Results before reranking"""
    
    top_n: int = 5
    """Results after reranking"""


async def _embed_repository(
    repo_url: str,
    chunk_size: int = 650
) -> Dict[str, Any]:
    """
    Internal function to embed a repository.
    
    Args:
        repo_url: Repository URL
        chunk_size: Lines per chunk
        
    Returns:
        Embedding statistics
    """
    from ..shared.pinecone_service import get_pinecone_service
    from ..shared.repo_downloader import get_downloader
    
    try:
        logger.info(f"🚀 Starting repository embedding for {repo_url}")
        
        # Get repo downloader and Pinecone service
        downloader = get_downloader()
        pinecone_service = await get_pinecone_service()
        
        # Download repository
        repo_path = await downloader.download_repo(repo_url)
        logger.info(f"📥 Repository downloaded to {repo_path}")
        
        # Get repository ID from URL
        repo_id = repo_url.rstrip('/').split('/')[-1]
        
        # Get all Python files
        python_files = downloader.get_all_python_files(repo_path)
        logger.info(f"📂 Found {len(python_files)} Python files")
        
        # Process files and create chunks
        all_chunks = []
        files_processed = 0
        
        for file_path in python_files:
            # Skip test files
            if '/tests/' in file_path or '/test_' in file_path:
                continue
            
            try:
                # Get relative file path
                rel_path = downloader.get_relative_path(file_path, repo_path)
                file_name = Path(file_path).name
                
                # Read file
                content = downloader.read_file(file_path)
                
                # Split into chunks
                chunks = pinecone_service.split_code_into_chunks(
                    content=content,
                    file_name=file_name,
                    file_path=rel_path,
                    chunk_size=chunk_size
                )
                
                all_chunks.extend(chunks)
                files_processed += 1
                
                if files_processed % 10 == 0:
                    logger.info(f"  ✓ Processed {files_processed} files, {len(all_chunks)} chunks total")
                    
            except Exception as e:
                logger.warning(f"⚠️ Failed to process {file_path}: {str(e)}")
                continue
        
        logger.info(f"✅ Created {len(all_chunks)} chunks from {files_processed} files")
        
        # Upload to Pinecone
        logger.info(f"📦 Uploading {len(all_chunks)} chunks to Pinecone...")
        result = await pinecone_service.add_code_documents(
            repo_id=repo_id,
            documents=all_chunks
        )
        
        logger.info(f"✅ Embedding complete!")
        return {
            "success": True,
            "repo_id": repo_id,
            "repo_url": repo_url,
            "files_processed": files_processed,
            "chunks_created": result['chunks_created'],
            "stats": result['stats']
        }
        
    except Exception as e:
        logger.error(f"❌ Embedding failed: {str(e)}")
        raise


@router.post("/create")
async def create_embeddings(
    request: EmbedRequest,
    background_tasks: BackgroundTasks
):
    """
    Create vector embeddings for a repository.
    
    This endpoint:
    1. Downloads repository from GitHub
    2. Splits Python files into 650-line chunks
    3. Generates embeddings using all-MiniLM-L6-v2
    4. Stores in Pinecone with file metadata
    5. Enables semantic search + reranking
    
    Args:
        request: Embedding request with repo_url
        background_tasks: Background tasks handler
        
    Returns:
        Embedding statistics and file count
    """
    try:
        logger.info(f"📝 Embedding request for {request.repo_url}")
        
        # Run embedding in background (don't block)
        background_tasks.add_task(
            _embed_repository,
            repo_url=request.repo_url,
            chunk_size=request.chunk_size
        )
        
        return {
            "success": True,
            "message": "Embedding started in background",
            "repo_url": request.repo_url,
            "status": "processing"
        }
        
    except Exception as e:
        logger.error(f"❌ Embedding creation failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/search")
async def semantic_search(request: SearchRequest):
    """
    Semantic search with Cohere reranking.
    
    This endpoint:
    1. Generates embedding for query
    2. Searches Pinecone for similar chunks
    3. Reranks with Cohere for relevance
    4. Returns citations with file locations
    
    Args:
        request: Search request with query and repo_id
        
    Returns:
        Ranked search results with citations
    """
    try:
        logger.info(f"🔍 Search request: '{request.query}' in repo {request.repo_id}")
        
        from ..shared.pinecone_service import get_pinecone_service
        
        pinecone_service = await get_pinecone_service()
        
        # Complete search pipeline
        results = await pinecone_service.search_with_reranking(
            query=request.query,
            repo_id=request.repo_id,
            top_k=request.top_k,
            top_n=request.top_n
        )
        
        return {
            "success": True,
            "query": request.query,
            "repo_id": request.repo_id,
            "results_count": len(results),
            "results": results
        }
        
    except Exception as e:
        logger.error(f"❌ Search failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/rerank")
async def rerank_results(
    query: str,
    results: List[Dict[str, Any]]
):
    """
    Rerank search results with Cohere.
    
    Takes existing search results and reranks them
    for better relevance to the query.
    
    Args:
        query: Search query
        results: Search results from Pinecone
        
    Returns:
        Reranked results ordered by relevance
    """
    try:
        logger.info(f"🔄 Reranking {len(results)} results for query: '{query}'")
        
        from ..shared.pinecone_service import get_pinecone_service
        
        pinecone_service = await get_pinecone_service()
        
        # Rerank results
        reranked = await pinecone_service.rerank_results(query, results)
        
        return {
            "success": True,
            "query": query,
            "reranked_count": len(reranked),
            "results": reranked
        }
        
    except Exception as e:
        logger.error(f"❌ Reranking failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats")
async def get_stats(repo_id: Optional[str] = None):
    """
    Get Pinecone index statistics.
    
    Args:
        repo_id: Optional repository ID for specific stats
        
    Returns:
        Index statistics including vector count
    """
    try:
        from ..shared.pinecone_service import get_pinecone_service
        
        pinecone_service = await get_pinecone_service()
        stats = await pinecone_service.get_index_stats()
        
        return {
            "success": True,
            "stats": stats
        }
        
    except Exception as e:
        logger.error(f"❌ Failed to get stats: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/delete")
async def delete_repository(repo_id: str):
    """
    Delete all embeddings for a repository.
    
    Warning: This is destructive and cannot be undone.
    
    Args:
        repo_id: Repository ID to delete
        
    Returns:
        Confirmation message
    """
    try:
        logger.warning(f"🗑️ Delete request for repo {repo_id}")
        
        from ..shared.pinecone_service import get_pinecone_service
        
        pinecone_service = await get_pinecone_service()
        success = await pinecone_service.delete_repository(repo_id)
        
        if success:
            return {
                "success": True,
                "message": f"Repository {repo_id} deleted from Pinecone"
            }
        else:
            raise HTTPException(status_code=500, detail="Delete failed")
            
    except Exception as e:
        logger.error(f"❌ Delete failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))