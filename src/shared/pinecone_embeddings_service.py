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
            raise ImportError("pinecone package required: pip install pinecone-client")
        if not TRANSFORMERS_AVAILABLE:
            raise ImportError("sentence-transformers package required: pip install sentence-transformers")
        if not COHERE_AVAILABLE:
            raise ImportError("cohere package required: pip install cohere")
        
        # Pinecone configuration
        self.pinecone_api_key = os.getenv("PINECONE_API_KEY")
        self.pinecone_index_name = os.getenv("PINECONE_INDEX_NAME", "code-search")
        
        if not self.pinecone_api_key:
            raise ValueError("PINECONE_API_KEY environment variable not set")
        
        # Initialize Pinecone
        try:
            self.pc = PineconeClient(api_key=self.pinecone_api_key)
            self.index = self.pc.Index(self.pinecone_index_name)
            logger.info(f"✅ Pinecone connected to index: {self.pinecone_index_name}")
        except Exception as e:
            logger.error(f"Failed to connect to Pinecone: {e}")
            raise
        
        # Initialize embedding model
        try:
            self.embedding_model = SentenceTransformer('all-MiniLM-L6-v2')
            logger.info("✅ Embedding model loaded: all-MiniLM-L6-v2")
        except Exception as e:
            logger.error(f"Failed to load embedding model: {e}")
            raise
        
        # Initialize Cohere reranker
        self.cohere_api_key = os.getenv("COHERE_API_KEY")
        if self.cohere_api_key:
            try:
                self.cohere_client = cohere.ClientV2(api_key=self.cohere_api_key)
                logger.info("✅ Cohere reranker initialized")
            except Exception as e:
                logger.warning(f"Failed to initialize Cohere: {e}")
                self.cohere_client = None
        else:
            logger.warning("⚠️ COHERE_API_KEY not set - reranking disabled")
            self.cohere_client = None
    
    async def embed_chunks(
        self,
        chunks: List[CodeChunk],
        batch_size: int = 32
    ) -> List[Dict[str, Any]]:
        """
        Generate embeddings for code chunks.
        
        Args:
            chunks: List of CodeChunk objects
            batch_size: Process embeddings in batches
            
        Returns:
            List of upsert-ready vectors
        """
        logger.info(f"🧬 Generating embeddings for {len(chunks)} chunks...")
        
        vectors = []
        
        # Process in batches
        for i in range(0, len(chunks), batch_size):
            batch = chunks[i:i + batch_size]
            batch_num = (i // batch_size) + 1
            
            # Extract content for embedding
            contents = [chunk.content for chunk in batch]
            
            # Generate embeddings (sync call in async context)
            embeddings = await asyncio.to_thread(
                self.embedding_model.encode,
                contents,
                convert_to_tensor=False
            )
            
            # Create vectors with metadata
            for chunk, embedding in zip(batch, embeddings):
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
            
            logger.info(f"  ✓ Batch {batch_num}: {len(batch)} embeddings generated")
        
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
        logger.info(f"🔍 Semantic search: '{query[:100]}' in repo {repo_id}")
        
        # Generate query embedding
        query_embedding = await asyncio.to_thread(
            self.embedding_model.encode,
            query,
            convert_to_tensor=False
        )
        
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
        if not self.cohere_client or not results:
            logger.warning("Cohere not available or no results to rerank")
            return results
        
        logger.info(f"🔄 Reranking {len(results)} results with Cohere...")
        
        try:
            # Prepare documents for reranking
            documents = [
                f"File: {r['metadata'].get('file_path', 'unknown')}\n"
                f"Lines {r['metadata'].get('start_line', '?')}-{r['metadata'].get('end_line', '?')}\n"
                f"Preview: {r['metadata'].get('content_preview', '')}"
                for r in results
            ]
            
            # Cohere rerank
            response = await asyncio.to_thread(
                self.cohere_client.rerank,
                model="rerank-english-v2.0",
                query=query,
                documents=documents,
                top_n=min(5, len(results))
            )
            
            # Map back to original results
            reranked_results = []
            for rank_result in response.results:
                original = results[rank_result.index]
                reranked_results.append({
                    **original,
                    "relevance_score": rank_result.relevance_score
                })
            
            logger.info(f"  ✓ Reranking complete: {len(reranked_results)} results")
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
        reranked = await self.rerank_results(query, results)
        
        # Step 3: Format citations
        citations = [
            {
                "file": r['metadata'].get('file_path', 'unknown'),
                "file_name": r['metadata'].get('file_name', 'unknown'),
                "lines": f"{r['metadata'].get('start_line', '?')}-{r['metadata'].get('end_line', '?')}",
                "language": r['metadata'].get('language', 'python'),
                "preview": r['metadata'].get('content_preview', ''),
                "relevance": r.get('relevance_score', r.get('score', 0)),
                "chunk_id": r['id']
            }
            for r in reranked
        ]
        
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
        try:
            stats = await asyncio.to_thread(self.index.describe_index_stats)
            
            return {
                "total_vectors": stats.get('total_vector_count', 0),
                "index_name": self.pinecone_index_name,
                "dimension": 384,  # all-MiniLM-L6-v2 dimension
                "metric": "cosine",
                "namespaces": stats.get('namespaces', {})
            }
        except Exception as e:
            logger.error(f"Failed to get stats: {e}")
            return {}
    
    async def delete_repository(self, repo_id: str) -> bool:
        """
        Delete all embeddings for a repository.
        
        Args:
            repo_id: Repository ID
            
        Returns:
            Success status
        """
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