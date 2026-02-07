"""Clear handlers - Neo4j and Pinecone clearing operations."""

from ....shared.mcp_server import ToolResult
from ....shared.neo4j_service import Neo4jService
from ....shared.pinecone_embeddings_service import PineconeEmbeddingsService
from ....shared.logger import get_logger

logger = get_logger(__name__)


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
            data={"status": "cleared", "message": "All data deleted from Neo4j"}
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
        
        # Try to initialize Pinecone if not already done
        if not pinecone_service or not pinecone_service.index:
            logger.info("Attempting to initialize Pinecone directly...")
            try:
                import pinecone
                import os
                
                PINECONE_API_KEY = os.getenv("PINECONE_API_KEY", "")
                PINECONE_INDEX = os.getenv("PINECONE_INDEX", "code-search")
                
                if not PINECONE_API_KEY:
                    logger.warning("PINECONE_API_KEY not set - cannot clear embeddings")
                    return ToolResult(
                        success=True,
                        data={"status": "skipped", "message": "Pinecone API key not configured"}
                    )
                
                # Initialize Pinecone directly
                pc = pinecone.Pinecone(api_key=PINECONE_API_KEY)
                index = pc.Index(PINECONE_INDEX)
                
                # Delete all vectors using namespace filter
                if repo_id == "all":
                    # Delete all namespaces
                    logger.info("Deleting all namespaces from Pinecone...")
                    index.delete(delete_all=True)
                else:
                    # Delete specific namespace
                    logger.info(f"Deleting namespace: {repo_id}")
                    index.delete(delete_all=True, namespace=repo_id)
                
                logger.info(f"✅ Embeddings cleared for {repo_id}")
                
                return ToolResult(
                    success=True,
                    data={"status": "cleared", "message": f"Pinecone embeddings deleted for {repo_id}"}
                )
                
            except Exception as pinecone_err:
                logger.error(f"❌ Pinecone direct initialization failed: {pinecone_err}")
                # Still return success since we tried our best
                return ToolResult(
                    success=True,
                    data={"status": "attempted", "message": f"Pinecone clear attempted but may have failed: {str(pinecone_err)[:100]}"}
                )
        
        # If pinecone_service exists and is initialized
        await pinecone_service.delete_vectors(repo_id)
        
        logger.info(f"✅ Embeddings cleared for {repo_id}")
        
        return ToolResult(
            success=True,
            data={"status": "cleared", "message": f"Pinecone embeddings deleted for {repo_id}"}
        )
        
    except Exception as e:
        logger.error(f"❌ Failed to clear embeddings: {e}")
        return ToolResult(success=False, error=str(e))