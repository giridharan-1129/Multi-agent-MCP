"""Handler for relationship traversal."""

from ....shared.mcp_server import ToolResult

from ....shared.neo4j_service import Neo4jService
from ....shared.logger import get_logger

logger = get_logger(__name__)


async def trace_imports_handler(
    neo4j_service: Neo4jService,
    module_name: str
) -> ToolResult:
    """Trace import chains."""
    try:
        query = """
        MATCH path = (m:Module {name: $module})-[:IMPORTS*]->(imported)
        RETURN [node.name for node in nodes(path)] as import_chain
        LIMIT 5
        """
        
        result = await neo4j_service.execute_query(query, {"module": module_name})
        
        chains = [record[0] for record in result]
        
        logger.info(f"Import chains traced for {module_name}: {len(chains)}")
        
        return ToolResult(
            success=True,
            data={
                "module": module_name,
                "import_chains": chains,
                "count": len(chains)
            }
        )
    except Exception as e:
        logger.error(f"Failed to trace imports: {e}")
        return ToolResult(success=False, error=str(e))


async def find_related_handler(
    neo4j_service: Neo4jService,
    entity_name: str,
    relationship_type: str,
    direction: str = "outgoing"
) -> ToolResult:
    """Find related entities by relationship type."""
    try:
        if direction == "outgoing":
            query = f"MATCH (e {{name: $name}})-[:{relationship_type}]->(related) RETURN related.name"
        elif direction == "incoming":
            query = f"MATCH (e {{name: $name}})<-[:{relationship_type}]-(related) RETURN related.name"
        else:
            query = f"MATCH (e {{name: $name}})-[:{relationship_type}]-(related) RETURN related.name"
        
        query += " LIMIT 20"
        
        result = await neo4j_service.execute_query(query, {"name": entity_name})
        
        related = [record[0] for record in result]
        
        logger.info(f"Related entities found for {entity_name}: {len(related)}")
        
        return ToolResult(
            success=True,
            data={
                "entity": entity_name,
                "relationship": relationship_type,
                "direction": direction,
                "related": related,
                "count": len(related)
            }
        )
    except Exception as e:
        logger.error(f"Failed to find related: {e}")
        return ToolResult(success=False, error=str(e))
