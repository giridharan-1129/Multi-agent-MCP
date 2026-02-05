"""Handler for semantic search in Pinecone."""
import asyncio

from typing import Optional
from ....shared.mcp_server import ToolResult
from ....shared.pinecone_embeddings_service import PineconeEmbeddingsService, CodeChunker
from ....shared.repo_downloader import RepositoryDownloader
from ....shared.logger import get_logger

logger = get_logger(__name__)


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
        if not pinecone_service:
            logger.error("❌ Pinecone service is None")
            return ToolResult(
                success=True,
                data={
                    "query": query,
                    "repo_id": repo_id,
                    "chunks": [],
                    "count": 0,
                    "reranked": False,
                    "message": "Pinecone not initialized"
                }
            )
        
        # Check if index exists
        try:
            if not hasattr(pinecone_service, 'index') or pinecone_service.index is None:
                logger.warning("⚠️ Pinecone index attribute missing or None")
                return ToolResult(
                    success=True,
                    data={
                        "query": query,
                        "repo_id": repo_id,
                        "chunks": [],
                        "count": 0,
                        "reranked": False,
                        "message": "Pinecone index not available"
                    }
                )
        except AttributeError as attr_err:
            logger.error(f"❌ AttributeError checking Pinecone index: {attr_err}")
            return ToolResult(
                success=True,
                data={
                    "query": query,
                    "repo_id": repo_id,
                    "chunks": [],
                    "count": 0,
                    "reranked": False,
                    "message": "Pinecone attribute error"
                }
            )
        
        logger.info(f"🔍 Searching: '{query}' in repo {repo_id}")
        
        # DETAILED LOGGING
        logger.info(f"🔍 semantic_search_handler called")
        logger.info(f"   query: {query}")
        logger.info(f"   repo_id: {repo_id}")
        logger.info(f"   top_k: {top_k}")
        logger.info(f"   pinecone_service: {pinecone_service}")
        logger.info(f"   pinecone_service type: {type(pinecone_service)}")
        if pinecone_service:
            logger.info(f"   has index attr: {hasattr(pinecone_service, 'index')}")
            logger.info(f"   index value: {getattr(pinecone_service, 'index', 'NO ATTR')}")
            logger.info(f"   has cohere_client attr: {hasattr(pinecone_service, 'cohere_client')}")        
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
        chunks = [
            {
                "chunk_id": c.get("chunk_id"),
                "file_path": c.get("file"),
                "file_name": c.get("file").split("/")[-1],
                "start_line": int(c.get("lines", "0-0").split("-")[0]),
                "end_line": int(c.get("lines", "0-0").split("-")[1]),
                "language": c.get("language", "python"),
                "preview": c.get("preview", ""),
                "original_score": round(c.get("relevance", 0), 3),  # Pinecone score
                "relevance_score": round(c.get("relevance", 0), 3),  # Will update after reranking
                "confidence": round(c.get("relevance", 0), 3),  # Will update after reranking
                "lines": c.get("lines"),
                "reranked": False
            }
            for c in search_results
        ]
        
        logger.info(f"✅ Got {len(chunks)} initial results from Pinecone")
        
        # Step 2: Cohere reranking (if available)
        reranked = False
        if pinecone_service.cohere_client and len(chunks) > 0:
            try:
                logger.info(f"🔄 Step 2: Reranking with Cohere...")
                
                # Prepare documents for reranking
                documents = []
                for chunk in chunks:
                    doc = f"File: {chunk['file_path']}\n"
                    doc += f"Lines {chunk['start_line']}-{chunk['end_line']}\n"
                    doc += f"Language: {chunk['language']}\n"
                    doc += f"Content: {chunk['preview']}"
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
                            # Average the two scores
                            chunk["relevance_score"] = cohere_score  # Primary: Cohere score
                            chunk["confidence"] = round((original_score + cohere_score) / 2, 3)
                            chunk["reranked"] = True
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