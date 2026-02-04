"""Handler for class analysis."""

from ....shared.mcp_server import ToolResult

from ....shared.neo4j_service import Neo4jService
from ....shared.logger import get_logger

logger = get_logger(__name__)


async def analyze_class_handler(
    neo4j_service: Neo4jService,
    name: str
) -> ToolResult:
    """Analyze class structure and inheritance."""
    try:
        query = """
        MATCH (c:Class {name: $name})
        OPTIONAL MATCH (c)-[:CONTAINS]->(method:Function)
        OPTIONAL MATCH (c)-[:INHERITS_FROM]->(parent)
        OPTIONAL MATCH (child)-[:INHERITS_FROM]->(c)
        OPTIONAL MATCH (c)-[:HAS_PARAMETER]->(attr)
        RETURN c, collect(distinct method.name) as methods,
               collect(distinct parent.name) as parents,
               collect(distinct child.name) as subclasses,
               collect(distinct attr.name) as attributes
        """
        
        result = await neo4j_service.execute_query(query, {"name": name})
        
        if not result:
            return ToolResult(success=False, error=f"Class not found: {name}")
        
        record = result[0]
        cls = record[0]
        
        logger.info(f"Class analyzed: {name}")
        
        return ToolResult(
            success=True,
            data={
                "name": cls.get("name"),
                "docstring": cls.get("docstring", ""),
                "methods": record[1] or [],
                "parents": record[2] or [],
                "subclasses": record[3] or [],
                "attributes": record[4] or [],
                "line_count": cls.get("line_count", 0)
            }
        )
    except Exception as e:
        logger.error(f"Failed to analyze class: {e}")
        return ToolResult(success=False, error=str(e))
