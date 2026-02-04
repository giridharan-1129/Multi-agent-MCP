"""
Embeddings Handler - Pinecone vector indexing and semantic search.

Handles:
- Code chunking (650 lines)
- Embedding generation
- Pinecone storage
- Semantic search with reranking
"""

from typing import Any, Dict
from ...shared.mcp_server import ToolResult
from ...shared.pinecone_embeddings_service import PineconeEmbeddingsService, CodeChunker
from ...shared.repo_downloader import RepositoryDownloader
from ...shared.logger import get_logger

logger = get_logger(__name__)


async def embed_repository_handler(
    repo_url: str,
    repo_id: str,
    branch: str,
    pinecone_service: PineconeEmbeddingsService,
    code_chunker: CodeChunker,
    repo_downloader: RepositoryDownloader
) -> ToolResult:
    """
    Embed repository into Pinecone:
    1. Download repo
    2. Chunk Python files (650 lines)
    3. Generate embeddings
    4. Upsert to Pinecone
    """
    try:
        if not pinecone_service or not pinecone_service.index:
            return ToolResult(
                success=False,
                error="Pinecone service not initialized. Set PINECONE_API_KEY."
            )
        
        logger.info(f"🚀 Embedding repository: {repo_url} (ID: {repo_id})")
        
        # Step 1: Download
        logger.info(f"📥 Downloading...")
        repo_path = await repo_downloader.download_repo(repo_url)
        
        # Step 2: Get files
        py_files = repo_downloader.get_all_python_files(repo_path)
        logger.info(f"📁 Found {len(py_files)} Python files")
        
        # Step 3: Read and chunk
        logger.info(f"🔪 Chunking files (650 lines)...")
        files_dict = {}
        for py_file in py_files:
            try:
                content = repo_downloader.read_file(py_file)
                rel_path = repo_downloader.get_relative_path(py_file, repo_path)
                files_dict[rel_path] = content
            except Exception as e:
                logger.warning(f"Could not read {py_file}: {e}")
                continue
        
        # Chunk all files
        all_chunks = code_chunker.chunk_multiple_files(files_dict, repo_id)
        logger.info(f"✅ Created {len(all_chunks)} chunks")
        
        if not all_chunks:
            return ToolResult(
                success=False,
                error="No chunks created from files"
            )
        
        # Step 4: Generate embeddings
        logger.info(f"🧬 Generating embeddings...")
        vectors = await pinecone_service.embed_chunks(all_chunks, batch_size=32)
        logger.info(f"✅ Generated {len(vectors)} embeddings")
        
        # Step 5: Upsert to Pinecone
        logger.info(f"📤 Upserting to Pinecone...")
        upserted_count = await pinecone_service.upsert_to_pinecone(vectors, batch_size=100)
        logger.info(f"✅ Upserted {upserted_count} vectors")
        
        return ToolResult(
            success=True,
            data={
                "repo_url": repo_url,
                "repo_id": repo_id,
                "branch": branch,
                "statistics": {
                    "files_processed": len(files_dict),
                    "chunks_created": len(all_chunks),
                    "vectors_upserted": upserted_count,
                    "repo_id": repo_id
                }
            }
        )
        
    except Exception as e:
        logger.error(f"❌ Embedding failed: {e}")
        return ToolResult(success=False, error=str(e))


async def semantic_search_handler(
    query: str,
    repo_id: str,
    top_k: int,
    pinecone_service: PineconeEmbeddingsService
) -> ToolResult:
    """
    Semantic search in Pinecone with Cohere reranking.
    """
    try:
        if not pinecone_service or not pinecone_service.index:
            return ToolResult(
                success=False,
                error="Pinecone service not initialized"
            )
        
        logger.info(f"🔍 Searching: '{query}' in repo {repo_id}")
        
        # Search with reranking
        citations = await pinecone_service.search_with_reranking(
            query=query,
            repo_id=repo_id,
            top_k=top_k
        )
        
        # Format chunks
        chunks = [
            {
                "chunk_id": c.get("chunk_id"),
                "file_path": c.get("file"),
                "file_name": c.get("file").split("/")[-1],
                "start_line": int(c.get("lines", "0-0").split("-")[0]),
                "end_line": int(c.get("lines", "0-0").split("-")[1]),
                "language": c.get("language", "python"),
                "preview": c.get("preview", ""),
                "relevance_score": c.get("relevance", 0),
                "lines": c.get("lines")
            }
            for c in citations
        ]
        
        logger.info(f"✅ Found {len(chunks)} relevant chunks")
        
        return ToolResult(
            success=True,
            data={
                "query": query,
                "repo_id": repo_id,
                "chunks": chunks,
                "count": len(chunks)
            }
        )
        
    except Exception as e:
        logger.error(f"❌ Search failed: {e}")
        return ToolResult(success=False, error=str(e))


async def get_embeddings_stats_handler(
    repo_id: str,
    pinecone_service: PineconeEmbeddingsService
) -> ToolResult:
    """
    Get Pinecone index statistics.
    """
    try:
        logger.info("📊 Getting embeddings stats...")
        
        if not pinecone_service or not pinecone_service.index:
            logger.warning("Pinecone not initialized")
            return ToolResult(
                success=True,
                data={
                    "status": "unavailable",
                    "message": "Pinecone not configured - Set PINECONE_API_KEY",
                    "fallback": "Using Neo4j graph search"
                }
            )
        
        # Get stats
        stats = await pinecone_service.get_index_stats(repo_id)
        
        logger.info(f"✅ Stats: {stats.get('total_vectors', 0)} vectors")
        
        return ToolResult(
            success=True,
            data={
                "status": "available",
                "summary": {
                    "chunks_total": stats.get('total_vectors', 0),
                    "embedding_model": "text-embedding-3-small",
                    "reranker": "rerank-english-v3",
                    "status": "ready" if stats.get('total_vectors', 0) > 0 else "empty"
                },
                "stats": stats
            }
        )
        
    except Exception as e:
        logger.error(f"❌ Failed to get stats: {e}")
        return ToolResult(
            success=True,
            data={
                "status": "error",
                "error": str(e),
                "fallback": "Using Neo4j graph search"
            }
        )
