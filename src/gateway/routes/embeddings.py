"""
Embeddings Route - FastAPI endpoints for Pinecone vector indexing with 650-line chunking.

Handles:
- Code splitting into 650-line chunks
- Embedding with sentence-transformers
- Pinecone storage with metadata
- LLM-based reranking via OpenAI
"""

from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import os
import asyncio
import logging

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/embeddings", tags=["embeddings"])


class EmbedRequest(BaseModel):
    """Embedding request model."""
    repo_url: str
    chunk_size: int = 650


class SearchRequest(BaseModel):
    """Semantic search request."""
    repo_id: str
    query: str
    top_k: int = 10


async def _embed_repository(repo_url: str, chunk_size: int = 650) -> Dict[str, Any]:
    """
    Internal function to embed a repository.
    650-line chunks with metadata.
    """
    from ..shared.repo_downloader import get_downloader
    from ..shared.pinecone_embeddings_service import init_embeddings_service, CodeChunker
    
    try:
        logger.info(f"Starting repository embedding for {repo_url}")
        
        # Download repository
        downloader = get_downloader()
        repo_path = await downloader.download_repo(repo_url)
        logger.info(f"Repository downloaded to {repo_path}")
        
        # Extract repo ID from URL
        repo_id = repo_url.rstrip('/').split('/')[-1]
        
        # Get all Python files
        python_files = downloader.get_all_python_files(repo_path)
        logger.info(f"Found {len(python_files)} Python files")
        
        # Initialize chunker and embeddings service
        chunker = CodeChunker(chunk_size=chunk_size, overlap=50)
        embeddings_service = await init_embeddings_service()
        
        # Step 1: Create 650-line chunks from all files
        all_chunks = []
        for file_path in python_files:
            if '/tests/' in file_path or '/test_' in file_path:
                continue
            
            try:
                rel_path = downloader.get_relative_path(file_path, repo_path)
                file_name = file_path.split('/')[-1]
                content = downloader.read_file(file_path)
                
                file_chunks = chunker.chunk_file(
                    file_path=rel_path,
                    file_content=content,
                    repo_id=repo_id,
                    file_name=file_name
                )
                all_chunks.extend(file_chunks)
            except Exception as e:
                logger.warning(f"Failed to chunk {file_path}: {str(e)}")
                continue
        
        logger.info(f"Created {len(all_chunks)} chunks from {len(python_files)} files")
        
        # Step 2: Generate embeddings
        vectors = await embeddings_service.embed_chunks(all_chunks, batch_size=32)
        logger.info(f"Generated {len(vectors)} embeddings")
        
        # Step 3: Upsert to Pinecone
        upserted_count = await embeddings_service.upsert_to_pinecone(vectors, batch_size=100)
        logger.info(f"Upserted {upserted_count} vectors to Pinecone")
        
        # Step 4: Get index stats
        stats = await embeddings_service.get_index_stats()
        
        return {
            "success": True,
            "repo_id": repo_id,
            "repo_url": repo_url,
            "files_processed": len(python_files),
            "chunks_created": len(all_chunks),
            "embeddings_generated": len(vectors),
            "vectors_upserted": upserted_count,
            "stats": stats
        }
        
    except Exception as e:
        logger.error(f"Embedding failed: {str(e)}")
        raise


@router.post("/create")
async def create_embeddings(request: EmbedRequest, background_tasks: BackgroundTasks):
    """
    Create vector embeddings for a repository.
    
    Process:
    1. Download repository from GitHub
    2. Split Python files into 650-line chunks
    3. Generate embeddings using sentence-transformers
    4. Store in Pinecone with file metadata
    5. Enable semantic search + reranking
    """
    try:
        logger.info(f"Embedding request for {request.repo_url}")
        
        # Run embedding in background
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
        logger.error(f"Embedding creation failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/search")
async def semantic_search(request: SearchRequest):
    """
    Semantic search with LLM-based reranking.
    
    Process:
    1. Generate embedding for query
    2. Search Pinecone for similar chunks
    3. Rerank with OpenAI based on query intent
    4. Return citations with file locations
    """
    try:
        from ..shared.pinecone_embeddings_service import get_embeddings_service
        
        embeddings_service = get_embeddings_service()
        
        logger.info(f"Search request: '{request.query}' in repo {request.repo_id}")
        
        # Complete search pipeline with reranking
        results = await embeddings_service.search_with_reranking(
            query=request.query,
            repo_id=request.repo_id,
            top_k=request.top_k
        )
        
        return {
            "success": True,
            "query": request.query,
            "repo_id": request.repo_id,
            "results_count": len(results),
            "results": results
        }
        
    except Exception as e:
        logger.error(f"Search failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats")
async def get_stats(repo_id: Optional[str] = None):
    """Get Pinecone index statistics."""
    try:
        from ..shared.pinecone_embeddings_service import get_embeddings_service
        
        embeddings_service = get_embeddings_service()
        stats = await embeddings_service.get_index_stats()
        
        return {
            "success": True,
            "stats": stats
        }
        
    except Exception as e:
        logger.error(f"Failed to get stats: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/delete")
async def delete_repository(repo_id: str):
    """Delete all embeddings for a repository."""
    try:
        from ..shared.pinecone_embeddings_service import get_embeddings_service
        
        embeddings_service = get_embeddings_service()
        logger.warning(f"Delete request for repo {repo_id}")
        
        success = await embeddings_service.delete_repository(repo_id)
        
        if success:
            return {
                "success": True,
                "message": f"Repository {repo_id} deleted from Pinecone"
            }
        else:
            raise HTTPException(status_code=500, detail="Delete failed")
            
    except Exception as e:
        logger.error(f"Delete failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))