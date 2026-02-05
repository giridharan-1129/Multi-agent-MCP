"""Handler for dependency analysis."""

from ....shared.mcp_server import ToolResult

from ....shared.neo4j_service import Neo4jService
from ....shared.logger import get_logger

logger = get_logger(__name__)


async def get_dependencies_handler(
    neo4j_service: Neo4jService,
    name: str
) -> ToolResult:
    """Get what an entity depends on."""
    try:
        query = """
        MATCH (e {name: $name})-[r:DEPENDS_ON|IMPORTS|CALLS]->(dep)
        RETURN dep.name as dependency, type(r) as relationship_type
        LIMIT 20
        """
        
        result = await neo4j_service.execute_query(query, {"name": name})
        
        dependencies = [
            {"name": record["dependency"], "type": record["relationship_type"]}
            for record in result
        ]
        
        logger.info(f"Dependencies found for {name}: {len(dependencies)}")
        
        return ToolResult(
            success=True,
            data={
                "entity": name,
                "dependencies": dependencies,
                "count": len(dependencies)
            }
        )
    except Exception as e:
        logger.error(f"Failed to get dependencies: {e}")
        return ToolResult(success=False, error=str(e))


async def get_dependents_handler(
    neo4j_service: Neo4jService,
    name: str
) -> ToolResult:
    """Get what depends on an entity."""
    try:
        query = """
        MATCH (e {name: $name})<-[r:DEPENDS_ON|IMPORTS|CALLS]-(dependent)
        RETURN dependent.name as dependent, type(r) as relationship_type
        LIMIT 20
        """
        
        result = await neo4j_service.execute_query(query, {"name": name})
        
        dependents = [
            {"name": record["dependent"], "type": record["relationship_type"]}
            for record in result
        ]
        
        logger.info(f"Dependents found for {name}: {len(dependents)}")
        
        return ToolResult(
            success=True,
            data={
                "entity": name,
                "dependents": dependents,
                "count": len(dependents)
            }
        )
    except Exception as e:
        logger.error(f"Failed to get dependents: {e}")
        return ToolResult(success=False, error=str(e))
