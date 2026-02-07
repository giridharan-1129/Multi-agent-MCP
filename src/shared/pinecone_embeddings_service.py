"""
Pinecone Vector Embeddings Service with Cohere Reranking.

WHAT: Generate embeddings for code chunks and perform semantic search with reranking
WHY: Enable semantic search over code repositories beyond keyword matching
HOW: Split code into 650-line chunks, embed with sentence-transformers, rerank with Cohere

Features:
- 650-line code chunking with overlap
- Batch embedding generation
- Metadata storage (file path, line numbers, chunk info)
- Semantic search with Cohere reranking
- Citation generation from search results
"""

import os
import asyncio
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass
import logging

try:
    from sentence_transformers import SentenceTransformer
    TRANSFORMERS_AVAILABLE = True
except ImportError:
    TRANSFORMERS_AVAILABLE = False

try:
    from pinecone import Pinecone as PineconeClient
    PINECONE_AVAILABLE = True
except ImportError:
    PINECONE_AVAILABLE = False

try:
    import cohere
    COHERE_AVAILABLE = True
except ImportError:
    COHERE_AVAILABLE = False

logger = logging.getLogger(__name__)


@dataclass
class CodeChunk:
    """Represents a chunk of code with metadata."""
    chunk_id: str
    file_path: str
    file_name: str
    start_line: int
    end_line: int
    content: str
    language: str = "python"
    repo_id: str = ""
    
    def get_preview(self, max_chars: int = 300) -> str:
        """Get a preview of the chunk content."""
        preview = self.content[:max_chars]
        if len(self.content) > max_chars:
            preview += "..."
        return preview


class CodeChunker:
    """
    Split code files into 650-line chunks with metadata.
    
    Attributes:
        chunk_size: Number of lines per chunk (default: 650)
        overlap: Number of overlapping lines between chunks (default: 50)
    """
    
    def __init__(self, chunk_size: int = 650, overlap: int = 50):
        """
        Initialize code chunker.
        
        Args:
            chunk_size: Lines per chunk (default 650)
            overlap: Overlapping lines between chunks (default 50)
        """
        self.chunk_size = chunk_size
        self.overlap = overlap
        logger.info(f"CodeChunker initialized: {chunk_size} lines/chunk, {overlap} line overlap")
    
    def chunk_file(
        self,
        file_path: str,
        file_content: str,
        repo_id: str,
        file_name: str
    ) -> List[CodeChunk]:
        """
        Split a file into code chunks.
        
        Args:
            file_path: Relative path in repository (e.g., "fastapi/main.py")
            file_content: Full file content
            repo_id: Repository identifier
            file_name: Just the filename (e.g., "main.py")
            
        Returns:
            List of CodeChunk objects
        """
        lines = file_content.split('\n')
        total_lines = len(lines)
        chunks = []
        chunk_number = 1
        
        # Calculate step size (chunk_size minus overlap)
        step = self.chunk_size - self.overlap
        
        start_idx = 0
        while start_idx < total_lines:
            end_idx = min(start_idx + self.chunk_size, total_lines)
            chunk_lines = lines[start_idx:end_idx]
            chunk_content = '\n'.join(chunk_lines)
            
            # Create chunk ID: repo#filepath#chunk_number
            chunk_id = f"{repo_id}#{file_path}#{chunk_number}"
            
            chunk = CodeChunk(
                chunk_id=chunk_id,
                file_path=file_path,
                file_name=file_name,
                start_line=start_idx + 1,  # 1-indexed for display
                end_line=end_idx,
                content=chunk_content,
                repo_id=repo_id
            )
            
            chunks.append(chunk)
            logger.debug(
                f"  Chunk {chunk_number}: {file_name} lines {start_idx + 1}-{end_idx}"
            )
            
            # Move to next chunk
            start_idx += step
            chunk_number += 1
            
            # Stop if we've covered all content
            if end_idx >= total_lines:
                break
        
        logger.info(f"✓ {file_path}: {total_lines} lines → {len(chunks)} chunks")
        return chunks
    
    def chunk_multiple_files(
        self,
        files: Dict[str, str],
        repo_id: str
    ) -> List[CodeChunk]:
        """
        Chunk multiple files.
        
        Args:
            files: Dict of {file_path: file_content}
            repo_id: Repository ID
            
        Returns:
            List of all chunks from all files
        """
        all_chunks = []
        
        for file_path, content in files.items():
            file_name = file_path.split('/')[-1]
            file_chunks = self.chunk_file(
                file_path=file_path,
                file_content=content,
                repo_id=repo_id,
                file_name=file_name
            )
            all_chunks.extend(file_chunks)
        
        logger.info(f"✅ Chunked {len(files)} files into {len(all_chunks)} total chunks")
        return all_chunks


class PineconeEmbeddingsService:
    """
    Pinecone vector database service for code embeddings.
    
    Features:
    - Batch embedding generation
    - Semantic search with metadata filtering
    - Cohere reranking for better relevance
    - Citation generation
    """
    
    def __init__(self):
        """Initialize Pinecone embeddings service."""
        if not PINECONE_AVAILABLE:
            logger.warning("pinecone package not available: pip install pinecone-client")
            self.index = None
            return
        if not TRANSFORMERS_AVAILABLE:
            logger.warning("sentence-transformers package not available")
            self.index = None
            return
        if not COHERE_AVAILABLE:
            logger.warning("cohere package not available")
            self.index = None
            return
        
        # Pinecone configuration
        self.pinecone_api_key = os.getenv("PINECONE_API_KEY")
        self.pinecone_index_name = os.getenv("PINECONE_INDEX_NAME", "code-search")
        
        if not self.pinecone_api_key:
            logger.warning("PINECONE_API_KEY environment variable not set - embeddings disabled")
            self.index = None
            return
        
        # Initialize Pinecone
        try:
            self.pc = PineconeClient(api_key=self.pinecone_api_key)
            self.index = self.pc.Index(self.pinecone_index_name)
            logger.info(f"✅ Pinecone connected to index: {self.pinecone_index_name}")
        except Exception as e:
            logger.error(f"Failed to connect to Pinecone: {e}")
            # Don't raise - allow graceful degradation
            self.index = None
        
        # Initialize embedding model
        # Initialize OpenAI client for embeddings
        try:
            import openai
            self.openai_client = openai.OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
            self.embedding_model = None  # Will use OpenAI API
            logger.info("✅ Using OpenAI embeddings (1536 dim)")
        except Exception as e:
            logger.error(f"Failed to initialize OpenAI: {e}")
            self.openai_client = None
            raise
        
        # Initialize Cohere reranker
        self.cohere_api_key = os.getenv("COHERE_API_KEY")
        self.cohere_client = None
        
        if self.cohere_api_key:
            try:
                self.cohere_client = cohere.ClientV2(api_key=self.cohere_api_key)
                logger.info("✅ Cohere reranker initialized")
            except Exception as e:
                logger.warning(f"⚠️ Failed to initialize Cohere: {e}")
                self.cohere_client = None
        else:
            logger.warning("⚠️ COHERE_API_KEY not set - reranking will be skipped")
    
    async def embed_chunks(
        self,
        chunks: List[CodeChunk],
        batch_size: int = 32
    ) -> List[Dict[str, Any]]:
        """Generate embeddings for code chunks."""
        logger.info(f"🧬 Generating embeddings for {len(chunks)} chunks...")
        
        vectors = []
        
        # Process in batches
        for i in range(0, len(chunks), batch_size):
            batch = chunks[i:i + batch_size]
            batch_num = (i // batch_size) + 1
            
            # Extract and clean content
            contents = []
            batch_chunks = []
            
            for chunk in batch:
                content = chunk.content[:2000].strip()  # Truncate and strip whitespace
                if content:  # Only include non-empty content
                    contents.append(content)
                    batch_chunks.append(chunk)
            
            if not contents:
                logger.warning(f"Batch {batch_num}: All chunks empty, skipping")
                continue
            
            # Generate embeddings via OpenAI API
            def _get_embeddings():
                try:
                    response = self.openai_client.embeddings.create(
                        model="text-embedding-3-small",
                        input=contents,
                        encoding_format="float"
                    )
                    return [item.embedding for item in response.data]
                except Exception as e:
                    logger.error(f"OpenAI API error in batch {batch_num}: {e}")
                    raise
            
            try:
                embeddings = await asyncio.to_thread(_get_embeddings)
            except Exception as e:
                logger.error(f"Failed to generate embeddings for batch {batch_num}: {e}")
                continue  # Skip this batch, continue with next
            
            # Create vectors with metadata
            for chunk, embedding in zip(batch_chunks, embeddings):
                vector = {
                    "id": chunk.chunk_id,
                    "values": embedding.tolist() if hasattr(embedding, 'tolist') else embedding,
                    "metadata": {
                        "repo_id": chunk.repo_id,
                        "file_path": chunk.file_path,
                        "file_name": chunk.file_name,
                        "start_line": chunk.start_line,
                        "end_line": chunk.end_line,
                        "language": chunk.language,
                        "content_preview": chunk.get_preview(500),
                        "chunk_size_lines": chunk.end_line - chunk.start_line + 1
                    }
                }
                vectors.append(vector)
            
            logger.info(f"  ✓ Batch {batch_num}: {len(embeddings)} embeddings generated")
        
        logger.info(f"✅ Generated {len(vectors)} embeddings")
        return vectors
    
    async def upsert_to_pinecone(
        self,
        vectors: List[Dict[str, Any]],
        batch_size: int = 100
    ) -> int:
        """
        Upsert vectors to Pinecone.
        
        Args:
            vectors: List of vectors from embed_chunks
            batch_size: Upsert in batches
            
        Returns:
            Number of vectors upserted
        """
        if not vectors:
            logger.warning("No vectors provided for upsert")
            return 0
        
        if not self.index:
            logger.error("Pinecone index not initialized")
            return 0
        
        logger.info(f"📤 Upserting {len(vectors)} vectors to Pinecone...")
        
        upserted_count = 0
        
        for i in range(0, len(vectors), batch_size):
            batch = vectors[i:i + batch_size]
            batch_num = (i // batch_size) + 1
            
            try:
                # Upsert synchronously
                await asyncio.to_thread(self.index.upsert, vectors=batch)
                upserted_count += len(batch)
                logger.info(f"  ✓ Batch {batch_num}: {len(batch)} vectors upserted")
            except Exception as e:
                logger.error(f"Failed to upsert batch {batch_num}: {e}")
                raise
        
        logger.info(f"✅ Upserted {upserted_count} vectors successfully")
        return upserted_count
    
    async def semantic_search(
        self,
        query: str,
        repo_id: str,
        top_k: int = 10,
        filters: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """
        Semantic search with metadata filtering.
        
        Args:
            query: Search query
            repo_id: Repository ID to search in
            top_k: Number of results
            filters: Additional metadata filters
            
        Returns:
            List of search results with scores
        """
        if not query or not repo_id:
            logger.error("Query and repo_id are required for semantic search")
            return []
        
        if not self.openai_client or not self.index:
            logger.error("OpenAI client or Pinecone index not initialized")
            return []

        logger.info(f"🔍 Semantic search: '{query[:100]}' in repo {repo_id}")

        # Generate query embedding using OpenAI
        def _get_query_embedding():
            response = self.openai_client.embeddings.create(
                model="text-embedding-3-small",
                input=query,
                encoding_format="float"
            )
            return response.data[0].embedding

        query_embedding = await asyncio.to_thread(_get_query_embedding)
        
        # Build filter
        search_filter = {"repo_id": {"$eq": repo_id}}
        if filters:
            search_filter.update(filters)
        
        # Search Pinecone
        try:
            results = await asyncio.to_thread(
                self.index.query,
                vector=query_embedding.tolist() if hasattr(query_embedding, 'tolist') else query_embedding,
                top_k=top_k,
                include_metadata=True,
                filter=search_filter
            )
        except Exception as e:
            logger.error(f"Search failed: {e}")
            return []
        
        # Parse results
        search_results = []
        for match in results.get('matches', []):
            search_results.append({
                "id": match['id'],
                "score": match['score'],
                "metadata": match.get('metadata', {})
            })
        
        logger.info(f"  ✓ Found {len(search_results)} results")
        return search_results
    
    async def rerank_results(
        self,
        query: str,
        results: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Rerank search results using Cohere.
        
        Args:
            query: Original search query
            results: Initial search results
            
        Returns:
            Reranked results with relevance scores
        """
        if not query or not results:
            logger.warning("Query and results required for reranking")
            return results
        
        if not self.cohere_client:
            logger.warning("Cohere not available - skipping reranking")
            return results
        
        logger.info(f"🔄 Reranking {len(results)} results with Cohere...")
        
        try:
            # Prepare documents for reranking
            documents = []
            for r in results:
                metadata = r.get('metadata', {})
                doc = f"File: {metadata.get('file_path', 'unknown')}\n"
                doc += f"Lines {metadata.get('start_line', '?')}-{metadata.get('end_line', '?')}\n"
                doc += f"Preview: {metadata.get('content_preview', 'N/A')}"
                documents.append(doc)
            
            if not documents:
                logger.warning("No documents prepared for reranking")
                return results
            
            # Cohere rerank
            response = await asyncio.to_thread(
                self.cohere_client.rerank,
                model="rerank-english-v3",  # Updated model
                query=query,
                documents=documents,
                top_n=min(5, len(results))
            )
            
            if not response or not response.results:
                logger.warning("No reranking response from Cohere")
                return results
            
            # Map back to original results
            reranked_results = []
            for rank_result in response.results:
                if rank_result.index < len(results):
                    original = results[rank_result.index]
                    reranked_results.append({
                        **original,
                        "relevance_score": rank_result.relevance_score,
                        "reranked": True  # Mark as reranked
                    })

            logger.info(f"  ✓ Reranking complete: {len(reranked_results)} results")

            # Log top 3 reranked scores
            for i, r in enumerate(reranked_results[:3], 1):
                metadata = r.get('metadata', {})
                logger.info(f"    [{i}] {metadata.get('file_path', 'unknown')} | Reranked Score: {r.get('relevance_score', 0):.3f}")

            return reranked_results
            
        except Exception as e:
            logger.warning(f"Reranking failed: {e} - using original results")
            return results
    
    async def search_with_reranking(
        self,
        query: str,
        repo_id: str,
        top_k: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Complete search pipeline: semantic search + reranking.
        
        Args:
            query: Search query
            repo_id: Repository ID
            top_k: Number of results to fetch before reranking
            
        Returns:
            Reranked results with citations
        """
        if not query or not repo_id:
            logger.error("Query and repo_id required for search pipeline")
            return []
        
        logger.info(f"🔍 Starting search pipeline: '{query[:50]}...'")
        
        # Step 1: Semantic search
        results = await self.semantic_search(
            query=query,
            repo_id=repo_id,
            top_k=top_k
        )
        
        if not results:
            logger.warning("No results found in semantic search")
            return []
        
        # Step 2: Rerank (if Cohere available)
        # Step 2: Rerank (if Cohere available)
        reranked = await self.rerank_results(query, results)

        if self.cohere_client:
            logger.info(f"✅ Results reranked with Cohere (using rerank-english-v3)")
            for i, r in enumerate(reranked[:3], 1):
                logger.info(f"   [{i}] {r.get('metadata', {}).get('file_path', 'unknown')} | Score: {r.get('relevance_score', r.get('score', 0)):.3f}")
        else:
            logger.warning("⚠️ Cohere not available - using original search ranking")        
        # Step 3: Format citations
        # Step 3: Format citations
        citations = []
        for r in reranked:
            metadata = r.get('metadata', {})
            citation = {
                "type": "code_chunk",
                "file": metadata.get('file_path', 'unknown'),
                "file_name": metadata.get('file_name', 'unknown'),
                "lines": f"{metadata.get('start_line', '?')}-{metadata.get('end_line', '?')}",
                "language": metadata.get('language', 'python'),
                "preview": metadata.get('content_preview', 'N/A'),
                "relevance": r.get('relevance_score', r.get('score', 0)),
                "chunk_id": r.get('id', 'unknown')
            }
            citations.append(citation)
        
        logger.info(f"✅ Search complete: {len(citations)} citations")
        return citations
    
    async def get_index_stats(self, repo_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Get Pinecone index statistics.
        
        Args:
            repo_id: Optional repository ID to filter stats
            
        Returns:
            Index statistics
        """
        if not self.index:
            logger.error("Pinecone index not initialized")
            return {
                "total_vectors": 0,
                "index_name": self.pinecone_index_name,
                "dimension": 384,
                "metric": "cosine",
                "error": "Index not available"
            }
        
        try:
            stats = await asyncio.to_thread(self.index.describe_index_stats)
            
            return {
                "total_vectors": stats.get('total_vector_count', 0),
                "index_name": self.pinecone_index_name,
                "dimension": 1536,  # OpenAI text-embedding-3-small dimension
                "metric": "cosine",
                "namespaces": stats.get('namespaces', {})
            }
        except Exception as e:
            logger.error(f"Failed to get stats: {e}")
            return {}
    async def delete_vectors(self, repo_id: str = "all") -> int:
        """
        Delete vectors from Pinecone.
        
        Args:
            repo_id: Repository ID to delete ("all" = delete everything)
        
        Returns:
            Number of vectors deleted
        """
        try:
            if not self.index:
                logger.warning("Pinecone index not available")
                return 0
            
            if repo_id == "all":
                # Delete all vectors
                logger.info("🗑️ Deleting ALL vectors from Pinecone...")
                try:
                    self.index.delete(delete_all=True)
                    logger.info("✅ All vectors deleted successfully")
                except Exception as delete_err:
                    # If delete fails (e.g., 404 - namespace not found), that's OK
                    if "404" in str(delete_err) or "not found" in str(delete_err).lower():
                        logger.info("ℹ️ No vectors found to delete (index already empty)")
                    else:
                        logger.warning(f"⚠️ Delete encountered error (but continuing): {delete_err}")
                return 0  # Can't count when deleting all
            else:
                # Delete vectors for specific repo
                logger.info(f"🗑️ Deleting vectors for repo: {repo_id}")
                try:
                    # Filter by repo_id metadata
                    self.index.delete(
                        filter={"repo_id": {"$eq": repo_id}}
                    )
                    logger.info(f"✅ Vectors deleted for {repo_id}")
                except Exception as delete_err:
                    # If delete fails (e.g., 404 - namespace not found), that's OK
                    if "404" in str(delete_err) or "not found" in str(delete_err).lower():
                        logger.info(f"ℹ️ No vectors found for {repo_id} (already empty)")
                    else:
                        logger.warning(f"⚠️ Delete for {repo_id} encountered error: {delete_err}")
                return 0
                    
        except Exception as e:
            logger.error(f"❌ Unexpected error during delete: {e}")
            # Don't re-raise - return gracefully
            return 0

    async def delete_repository(self, repo_id: str) -> bool:
        """
        Delete all embeddings for a repository.
        
        Args:
            repo_id: Repository ID
            
        Returns:
            Success status
        """
        if not repo_id:
            logger.error("repo_id required for deletion")
            return False
        
        if not self.index:
            logger.error("Pinecone index not initialized")
            return False
        
        try:
            logger.warning(f"🗑️ Deleting all embeddings for repo {repo_id}...")
            
            # Delete by filter
            await asyncio.to_thread(
                self.index.delete,
                filter={"repo_id": {"$eq": repo_id}}
            )
            
            logger.info(f"✅ Repository {repo_id} deleted from Pinecone")
            return True
        except Exception as e:
            logger.error(f"Delete failed: {e}")
            return False


# Singleton instance
_embeddings_service: Optional[PineconeEmbeddingsService] = None


async def init_embeddings_service() -> PineconeEmbeddingsService:
    """
    Initialize embeddings service.
    
    Returns:
        PineconeEmbeddingsService instance
    """
    global _embeddings_service
    
    if _embeddings_service is None:
        try:
            _embeddings_service = PineconeEmbeddingsService()
        except Exception as e:
            logger.error(f"Failed to initialize embeddings service: {e}")
            raise
    
    return _embeddings_service


def get_embeddings_service() -> PineconeEmbeddingsService:
    """
    Get embeddings service instance (must be initialized first).
    
    Returns:
        PineconeEmbeddingsService instance
        
    Raises:
        RuntimeError: If service not initialized
    """
    global _embeddings_service
    
    if _embeddings_service is None:
        raise RuntimeError(
            "Embeddings service not initialized. Call init_embeddings_service() first."
        )
    
    return _embeddings_service