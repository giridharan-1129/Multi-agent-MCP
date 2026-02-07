"""
Status Handler - Graph statistics and clearing operations.

Handles:
- Get index status and statistics
- Clear Neo4j knowledge graph
"""
from ....shared.pinecone_embeddings_service import PineconeEmbeddingsService

from typing import Any, Dict
from ....shared.mcp_server import ToolResult

from ....shared.neo4j_service import Neo4jService
from ....shared.logger import get_logger

logger = get_logger(__name__)


async def get_index_status_handler(
    neo4j_service: Neo4jService
) -> ToolResult:
    """Get graph statistics and status."""
    try:
        logger.info("📊 Getting index status...")
        
        stats = await neo4j_service.get_graph_statistics()
        
        logger.info(f"✅ Status retrieved")
        
        return ToolResult(
            success=True,
            data={
                "status": "ok",
                "statistics": stats
            }
        )
        
    except Exception as e:
        logger.error(f"❌ Failed to get status: {e}")
        return ToolResult(success=False, error=str(e))

        
async def clear_index_handler(
    neo4j_service: Neo4jService
) -> ToolResult:
    """Clear all indexed data from Neo4j."""
    try:
        logger.warning("🗑️ Clearing knowledge graph...")
        
        query = "MATCH (n) DETACH DELETE n"
        await neo4j_service.execute_query(query, {})
        
        logger.info("✅ Knowledge graph cleared")
        
        return ToolResult(
            success=True,
            data={"status": "cleared", "message": "All data deleted"}
        )
        
    except Exception as e:
        logger.error(f"❌ Failed to clear: {e}")
        return ToolResult(success=False, error=str(e))
        
async def clear_embeddings_handler(
    pinecone_service: PineconeEmbeddingsService,
    repo_id: str = "all"
) -> ToolResult:
    """Clear all embeddings from Pinecone."""
    try:
        logger.warning(f"🗑️ Clearing Pinecone embeddings for repo: {repo_id}...")
        
        if not pinecone_service or not pinecone_service.index:
            logger.warning("Pinecone not initialized - skipping")
            return ToolResult(
                success=True,
                data={"status": "skipped", "message": "Pinecone not initialized"}
            )
        
        # Delete all vectors for the repo_id
        await pinecone_service.delete_vectors(repo_id)
        
        logger.info(f"✅ Embeddings cleared for {repo_id}")
        
        return ToolResult(
            success=True,
            data={"status": "cleared", "message": f"Pinecone embeddings deleted for {repo_id}"}
        )
        
    except Exception as e:
        logger.error(f"❌ Failed to clear embeddings: {e}")
        return ToolResult(success=False, error=str(e))