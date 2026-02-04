"""Handler for finding entities in Neo4j."""

from ....shared.mcp_server import ToolResult

from ....shared.neo4j_service import Neo4jService
from ....shared.logger import get_logger

logger = get_logger(__name__)


async def find_entity_handler(
    neo4j_service: Neo4jService,
    name: str,
    entity_type: str = None
) -> ToolResult:
    """Find entity by name and optional type."""
    try:
        query = "MATCH (e) WHERE e.name = $name"
        params = {"name": name}
        
        if entity_type:
            query += f" AND '{entity_type}' IN labels(e)"
        
        query += " RETURN e, labels(e) as types LIMIT 1"
        
        result = await neo4j_service.execute_query(query, params)
        
        if not result:
            return ToolResult(success=False, error=f"Entity not found: {name}")
        
        record = result[0]
        entity = record[0]
        
        logger.info(f"Entity found: {name}")
        
        return ToolResult(
            success=True,
            data={
                "name": entity.get("name"),
                "type": record[1][0] if record[1] else "Unknown",
                "properties": dict(entity)
            }
        )
    except Exception as e:
        logger.error(f"Failed to find entity: {e}")
        return ToolResult(success=False, error=str(e))
