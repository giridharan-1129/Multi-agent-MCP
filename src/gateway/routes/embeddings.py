"""
Embeddings Route - FastAPI endpoints for Pinecone vector indexing with 650-line chunking.

Handles:
- Code splitting into 650-line chunks
- Embedding with sentence-transformers
- Pinecone storage with metadata
- Cohere reranking
"""

from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
import os
import logging
from pathlib import Path
from ...shared.pinecone_embeddings_service import get_embeddings_service
from ...shared.logger import generate_correlation_id, set_correlation_id


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


async def embed_repository(repo_url: str, chunk_size: int = 650) -> Dict[str, Any]:
    """
    Internal function to embed a repository.
    650-line chunks with metadata.
    """
    from ...shared.repo_downloader import get_downloader
    from ...shared.pinecone_embeddings_service import init_embeddings_service, CodeChunker
    
    try:
        logger.info(f"🚀 Starting repository embedding for {repo_url}")
        
        # Download repository
        downloader = get_downloader()
        repo_path = await downloader.download_repo(repo_url)
        logger.info(f"📥 Repository downloaded to {repo_path}")
        
        # Extract repo ID from URL
        repo_id = repo_url.rstrip('/').split('/')[-1]
        logger.info(f"Repository ID: {repo_id}")
        
        # Get all Python files
        python_files = downloader.get_all_python_files(repo_path)
        logger.info(f"📁 Found {len(python_files)} Python files")
        
        if not python_files:
            logger.warning(f"No Python files found in {repo_url}")
            return {
                "success": False,
                "error": "No Python files found in repository",
                "repo_url": repo_url
            }
        
        # Initialize chunker and embeddings service
        logger.info(f"🔧 Initializing chunker (chunk_size={chunk_size}) and embeddings service")
        chunker = CodeChunker(chunk_size=chunk_size, overlap=50)
        
        try:
            embeddings_service = await init_embeddings_service()
            logger.info("✅ Embeddings service initialized")
        except Exception as e:
            logger.warning(f"⚠️ Pinecone not available: {str(e)}")
            logger.info("💡 For demo: Repository indexed in Neo4j. Semantic search disabled.")
            return {
                "success": False,
                "message": "Pinecone embeddings not configured",
                "fallback": "Neo4j graph search available",
                "repo_url": repo_url,
                "note": "For demo purposes, use Neo4j graph queries. Configure PINECONE_API_KEY to enable semantic search."
            }
        
        # Step 1: Create 650-line chunks from all files
        all_chunks = []
        files_processed = 0
        skipped_tests = 0
        
        for file_path in python_files:
            if '/tests/' in file_path or '/test_' in file_path:
                skipped_tests += 1
                continue
            
            try:
                rel_path = downloader.get_relative_path(file_path, repo_path)
                file_name = Path(file_path).name
                content = downloader.read_file(file_path)
                files_processed += 1
                
                file_chunks = chunker.chunk_file(
                    file_path=rel_path,
                    file_content=content,
                    repo_id=repo_id,
                    file_name=file_name
                )
                all_chunks.extend(file_chunks)
                
                if files_processed % 10 == 0:
                    logger.info(f"Progress: {files_processed} files processed, {len(all_chunks)} chunks created")
                    
            except Exception as e:
                logger.warning(f"Failed to chunk {file_path}: {str(e)}")
                continue
        
        logger.info(f"✅ Chunking complete: {files_processed} files, {skipped_tests} test files skipped, {len(all_chunks)} total chunks")
        
        if not all_chunks:
            logger.error("No chunks created from Python files")
            return {
                "success": False,
                "error": "No chunks created from Python files",
                "repo_url": repo_url,
                "files_processed": files_processed
            }
        
        # Step 2: Generate embeddings
        logger.info(f"🧬 Step 2: Generating embeddings for {len(all_chunks)} chunks")
        vectors = await embeddings_service.embed_chunks(all_chunks, batch_size=32)
        
        if not vectors:
            logger.error("Failed to generate embeddings")
            return {
                "success": False,
                "error": "Failed to generate embeddings",
                "repo_url": repo_url,
                "chunks_created": len(all_chunks)
            }
        
        logger.info(f"✅ Generated {len(vectors)} embeddings")
        logger.info(f"   Embeddings ready for Cohere reranking")

        # Step 3: Upsert to Pinecone
        logger.info(f"📤 Step 3: Upserting {len(vectors)} vectors to Pinecone")
        upserted_count = await embeddings_service.upsert_to_pinecone(vectors, batch_size=100)
        
        if upserted_count == 0:
            logger.error("Failed to upsert vectors to Pinecone")
            return {
                "success": False,
                "error": "Failed to upsert vectors to Pinecone",
                "repo_url": repo_url,
                "vectors_generated": len(vectors)
            }
        
        logger.info(f"✅ Upserted {upserted_count} vectors to Pinecone")
        
        # Step 4: Get index stats
        logger.info(f"📊 Step 4: Retrieving index statistics")
        stats = await embeddings_service.get_index_stats()
        
        logger.info(f"🎉 Embedding complete: {files_processed} files → {len(all_chunks)} chunks → {upserted_count} vectors")
        
        return {
            "success": True,
            "repo_id": repo_id,
            "repo_url": repo_url,
            "files_processed": files_processed,
            "chunks_created": len(all_chunks),
            "embeddings_generated": len(vectors),
            "vectors_upserted": upserted_count,
            "stats": stats
        }
        
    except Exception as e:
        logger.error(f"❌ Embedding failed: {str(e)}")
        return {
            "success": False,
            "error": str(e),
            "repo_url": repo_url
        }


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
    # Validate request
    if not request.repo_url:
        raise HTTPException(status_code=400, detail="repo_url is required")
    
    if request.chunk_size <= 0:
        raise HTTPException(status_code=400, detail="chunk_size must be > 0")
    
    # Validate repo URL format
    if not (request.repo_url.startswith('http://') or request.repo_url.startswith('https://')):
        raise HTTPException(status_code=400, detail="repo_url must be a valid HTTP(S) URL")
    
    try:
        logger.info(f"Embedding request for {request.repo_url}")
        
        # Run embedding in background
        background_tasks.add_task(
            embed_repository,
            repo_url=request.repo_url,
            chunk_size=request.chunk_size
        )
        
        return {
            "success": True,
            "message": "Embedding started in background",
            "repo_url": request.repo_url,
            "status": "processing"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Embedding creation failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/search")
async def semantic_search(request: SearchRequest):
    """
    Semantic search with Cohere reranking.
    
    Process:
    1. Generate embedding for query
    2. Search Pinecone for similar chunks
    3. Rerank with Cohere based on relevance
    4. Return citations with file locations
    """
    # Validate request
    if not request.query:
        raise HTTPException(status_code=400, detail="query is required")
    
    if not request.repo_id:
        raise HTTPException(status_code=400, detail="repo_id is required")
    
    if request.top_k <= 0:
        raise HTTPException(status_code=400, detail="top_k must be > 0")
    
    try:        
        embeddings_service = get_embeddings_service()
        
        logger.info(f"Search request: '{request.query}' in repo {request.repo_id}")
        
        # Complete search pipeline with reranking
        results = await embeddings_service.search_with_reranking(
            query=request.query,
            repo_id=request.repo_id,
            top_k=request.top_k
        )
        
        logger.info(f"Search complete: {len(results)} results found")
        
        return {
            "success": True,
            "query": request.query,
            "repo_id": request.repo_id,
            "results_count": len(results),
            "results": results
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Search failed: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/stats")
async def get_stats(repo_id: Optional[str] = None):
    """
    Get Pinecone index statistics for UI display.
    """
    try:
        # Check if Pinecone is configured
        if not os.getenv("PINECONE_API_KEY"):
            return {
                "success": False,
                "status": "unavailable",
                "message": "Pinecone not configured (PINECONE_API_KEY not set)",
                "fallback": "Using Neo4j graph search only"
            }
        
        embeddings_service = get_embeddings_service()
        
        # Check if embeddings service exists and has index
        if embeddings_service is None or not hasattr(embeddings_service, 'index'):
            logger.warning("Pinecone service not initialized")
            return {
                "success": False,
                "status": "unavailable",
                "message": "Pinecone not configured - embeddings service failed to initialize",
                "fallback": "Using Neo4j graph search only"
            }
        
        if not embeddings_service.index:
            logger.warning("Pinecone index not available")
            return {
                "success": False,
                "status": "unavailable",
                "message": "Pinecone not configured",
                "fallback": "Using Neo4j graph search only"
            }
        
        # Get Pinecone stats
        stats = await embeddings_service.get_index_stats(repo_id=repo_id)
        
        if not stats:
            logger.warning("No stats returned from embeddings service")
            return {
                "success": False,
                "status": "unavailable",
                "message": "Failed to retrieve Pinecone stats",
                "fallback": "Using Neo4j graph search only"
            }
        
        logger.info(f"Pinecone stats retrieved: {stats.get('total_vectors', 0)} vectors")
        
        # Extract primitive values to avoid serialization errors
        total_vectors = stats.get('total_vectors', 0)
        has_cohere = embeddings_service.cohere_client is not None
        
        # Build summary for UI - only include serializable data
        summary = {
            "repos_indexed": 1 if total_vectors > 0 else 0,
            "chunks_total": total_vectors,
            "embedding_model": "text-embedding-3-small (1536 dim)",
            "reranker": "rerank-english-v3 (Cohere)" if has_cohere else "None (disabled)",
            "status": "✅ Ready" if total_vectors > 0 else "⏳ Empty"
        }
        
        # Only return serializable stats data (no client objects)
        clean_stats = {
            "total_vectors": stats.get('total_vectors', 0),
            "index_name": stats.get('index_name', 'code-search'),
            "dimension": stats.get('dimension', 1536),
            "metric": stats.get('metric', 'cosine')
        }
        
        return {
            "success": True,
            "status": "available",
            "stats": clean_stats,
            "summary": summary
        }
        
    except Exception as e:
        logger.error(f"Failed to get Pinecone stats: {str(e)}")
        return {
            "success": False,
            "status": "error",
            "error": str(e),
            "fallback": "Using Neo4j graph search only"
        }

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
        # Check if Pinecone is configured
        if not os.getenv("PINECONE_API_KEY"):
            return {
                "success": False,
                "error": "Pinecone not configured",
                "message": "PINECONE_API_KEY environment variable not set"
            }
        
        logger.warning(f"🗑️ Delete request for repo {repo_id}")
        
        embeddings_service = get_embeddings_service()
        
        if not embeddings_service.index:
            return {
                "success": False,
                "error": "Pinecone index not available",
                "message": "Embeddings service not initialized"
            }
        
        success = await embeddings_service.delete_repository(repo_id)
        
        if success:
            return {
                "success": True,
                "message": f"Repository {repo_id} deleted from Pinecone",
                "index_name": embeddings_service.pinecone_index_name,
                "deleted_count": 0  # Would need to track actual count
            }
        else:
            raise HTTPException(status_code=500, detail="Delete failed")
            
    except Exception as e:
        logger.error(f"Delete failed: {str(e)}")
        return {
            "success": False,
            "error": str(e),
            "message": "Failed to delete repository from Pinecone"
        }