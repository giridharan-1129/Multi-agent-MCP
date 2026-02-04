"""Handler for custom Cypher query execution."""

from typing import Dict, Any
from ....shared.mcp_server import ToolResult

from ....shared.neo4j_service import Neo4jService
from ....shared.logger import get_logger

logger = get_logger(__name__)


async def execute_query_handler(
    neo4j_service: Neo4jService,
    query: str,
    parameters: Dict[str, Any] = None
) -> ToolResult:
    """Execute custom Cypher query with safety checks."""
    try:
        # Safety check: disallow write operations
        dangerous_keywords = ["CREATE", "DELETE", "SET", "DROP", "ALTER"]
        if any(keyword in query.upper() for keyword in dangerous_keywords):
            return ToolResult(
                success=False,
                error="Write operations not allowed"
            )
        
        result = await neo4j_service.execute_query(
            query,
            parameters or {}
        )
        
        logger.info(f"Query executed, results: {len(result)}")
        
        return ToolResult(
            success=True,
            data={
                "results": result,
                "count": len(result)
            }
        )
    except Exception as e:
        logger.error(f"Failed to execute query: {e}")
        return ToolResult(success=False, error=str(e))
