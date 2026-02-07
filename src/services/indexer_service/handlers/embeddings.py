"""
Embeddings Handler - Pinecone vector indexing and semantic search.

Handles:
- Code chunking (650 lines)
- Embedding generation
- Pinecone storage
- Semantic search with reranking
"""
import asyncio

from typing import Any, Dict
from ....shared.mcp_server import ToolResult

from ....shared.pinecone_embeddings_service import PineconeEmbeddingsService, CodeChunker
from ....shared.repo_downloader import RepositoryDownloader
from ....shared.logger import get_logger

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

        
        # Check if Pinecone is actually available
        try:
            if not pinecone_service:
                return ToolResult(
                    success=False,
                    error="Pinecone service not initialized"
                )
            if not hasattr(pinecone_service, 'index') or pinecone_service.index is None:
                logger.warning("Pinecone index not available")
                return ToolResult(
                    success=True,
                    data={
                        "query": query,
                        "repo_id": repo_id,
                        "chunks": [],
                        "count": 0,
                        "reranked": False,
                        "message": "Pinecone not initialized - no semantic search available"
                    }
                )
        except AttributeError:
            logger.warning("Pinecone service attribute error")
            return ToolResult(
                success=True,
                data={
                    "query": query,
                    "repo_id": repo_id,
                    "chunks": [],
                    "count": 0,
                    "reranked": False,
                    "message": "Pinecone service error"
                }
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
    
    Returns chunks with:
    - original_score: Pinecone embedding similarity (0-1)
    - relevance_score: Cohere reranked score (if available)
    - confidence: Average confidence (0-1)
    - reranked: Boolean flag
    """
    try:
        if not pinecone_service or not pinecone_service.index:
            return ToolResult(
                success=False,
                error="Pinecone service not initialized"
            )
        
        logger.info(f"🔍 Searching: '{query}' in repo {repo_id}")
        
        # Step 1: Semantic search
        logger.info(f"📍 Step 1: Pinecone semantic search...")
        search_results = await pinecone_service.semantic_search(
            query=query,
            repo_id=repo_id,
            top_k=top_k
        )
        
        if not search_results:
            logger.warning(f"⚠️ No search results found")
            return ToolResult(
                success=True,
                data={
                    "query": query,
                    "repo_id": repo_id,
                    "chunks": [],
                    "count": 0,
                    "reranked": False
                }
            )
        
        # Format initial chunks with original scores
        chunks = []
        for c in search_results:
            try:
                # Extract metadata from nested structure
                metadata = c.get("metadata", {})

                # Get file info from metadata
                file_path = metadata.get("file_path") or metadata.get("file") or "unknown"
                file_name = metadata.get("file_name") or (file_path.split("/")[-1] if file_path != "unknown" else "unknown")

                # Get line numbers from metadata
                start_line = metadata.get("start_line", 0)
                end_line = metadata.get("end_line", 0)
                lines_str = f"{start_line}-{end_line}" if (start_line or end_line) else "0-0"
                # Get relevance score (from top-level 'score' key, not metadata)
                original_relevance = c.get("score", 0)
                original_relevance = float(original_relevance) if original_relevance else 0.0

                # Get other metadata
                language = metadata.get("language", "python")
                preview = metadata.get("content_preview", "")[:300]
                chunk_content = metadata.get("content") or preview
                
                # Get original relevance score as DECIMAL (0-1)
                original_relevance = c.get("relevance_score") or c.get("relevance") or c.get("score", 0)
                original_relevance = float(original_relevance) if original_relevance else 0.0

                # Parse lines if string format
                if isinstance(lines_str, str) and "-" in lines_str:
                    try:
                        lines_parts = lines_str.split("-")
                        start_line = int(lines_parts[0]) if len(lines_parts) > 0 else 0
                        end_line = int(lines_parts[1]) if len(lines_parts) > 1 else 0
                    except (ValueError, IndexError):
                        pass

                # Create chunk ONCE with decimal scores (0-1 range)
                chunk = {
                    "chunk_id": c.get("id", ""),  # Use 'id' not 'chunk_id'
                    "file_path": file_path,
                    "file_name": file_name,
                    "start_line": start_line,
                    "end_line": end_line,
                    "language": language,
                    "preview": preview,
                    "content": chunk_content,
                    "original_score": round(original_relevance, 3),
                    "relevance_score": round(original_relevance, 3),
                    "confidence": round(original_relevance, 3),
                    "lines": lines_str,
                    "reranked": False
                }
                chunks.append(chunk)
                logger.info(f"   ✅ Chunk: {file_name} (Lines {start_line}-{end_line}, Relevance: {chunk['original_score']:.1%})")
                logger.info(f"   🔍 DEBUG - Raw chunk keys: {list(c.keys())}")
                logger.info(f"   🔍 DEBUG - Raw chunk: {c}")
            except Exception as chunk_err:
                logger.warning(f"⚠️ Skipping malformed chunk: {chunk_err}")
                continue
        
        
        logger.info(f"✅ Got {len(chunks)} initial results from Pinecone")
        
        # Step 2: Cohere reranking (if available)
        reranked = False
        if pinecone_service.cohere_client and len(chunks) > 0:
            try:
                logger.info(f"🔄 Step 2: Reranking with Cohere...")
                
                # Prepare documents for reranking with better formatting
                documents = []
                for chunk in chunks:
                    # Create comprehensive document for better reranking
                    doc = f"File: {chunk['file_path']}\n"
                    doc += f"Lines {chunk['start_line']}-{chunk['end_line']}\n"
                    doc += f"Language: {chunk['language']}\n"
                    # Include full content, not just preview, for better scoring
                    content = chunk.get("content") or chunk.get("preview", "")
                    if content:
                        doc += f"\nCode:\n{content[:1000]}"  # Include up to 1000 chars of actual code
                    documents.append(doc)
                
                # Call Cohere rerank
                logger.info(f"📤 Sending {len(documents)} documents to Cohere...")
                response = await asyncio.to_thread(
                    pinecone_service.cohere_client.rerank,
                    model="rerank-english-v3.0",
                    query=query,
                    documents=documents,
                    top_n=min(len(chunks), top_k)
                )
                
                if response and response.results:
                    logger.info(f"✅ Cohere returned {len(response.results)} reranked results")
                    
                    # Map reranked results
                    reranked_map = {}
                    for rank_result in response.results:
                        idx = rank_result.index
                        score = rank_result.relevance_score
                        if idx < len(chunks):
                            reranked_map[idx] = round(score, 3)
                    
                    # Update chunks with reranking scores
                    for idx, chunk in enumerate(chunks):
                        if idx in reranked_map:
                            cohere_score = reranked_map[idx]
                            original_score = chunk["original_score"]
                            # Weight: 70% Cohere (better semantic understanding) + 30% Pinecone (initial relevance)
                            weighted_score = round((cohere_score * 0.7) + (original_score * 0.3), 3)
                            chunk["relevance_score"] = weighted_score  # Primary: Weighted score
                            chunk["confidence"] = weighted_score
                            chunk["reranked"] = True
                            logger.info(f"   📊 Reranked: {chunk['file_name']} "
                                f"(Pinecone: {original_score:.1%}, Cohere: {cohere_score:.1%}, Final: {weighted_score:.1%})")
                            logger.debug(
                                f"📊 Reranked: {chunk['file_name']} "
                                f"(Pinecone: {original_score}, Cohere: {cohere_score}, Confidence: {chunk['confidence']})"
                            )
                        else:
                            chunk["confidence"] = chunk["original_score"]
                    
                    # Sort by reranked score descending
                    chunks.sort(key=lambda x: x["relevance_score"], reverse=True)
                    reranked = True
                    logger.info(f"✅ Reranking complete - sorted by relevance")
                else:
                    logger.warning("⚠️ Cohere returned empty response")
            
            except Exception as rerank_err:
                logger.warning(f"⚠️ Cohere reranking failed, using original scores: {rerank_err}")
                # Fall back to original scores
                for chunk in chunks:
                    chunk["confidence"] = chunk["original_score"]
        else:
            logger.info("ℹ️ Cohere not available - using Pinecone scores only")
            # No Cohere - use original scores
            for chunk in chunks:
                chunk["confidence"] = chunk["original_score"]
        
        logger.info(f"✅ Final results: {len(chunks)} chunks (reranked: {reranked})")
        
        return ToolResult(
            success=True,
            data={
                "query": query,
                "repo_id": repo_id,
                "chunks": chunks,
                "count": len(chunks),
                "reranked": reranked,
                "reranker_model": "rerank-english-v3.0" if reranked else None
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
