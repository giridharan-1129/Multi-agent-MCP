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
        OPTIONAL MATCH (c)-[:HAS_METHOD]->(method:Function)
        OPTIONAL MATCH (c)-[:INHERITS_FROM]->(parent)
        OPTIONAL MATCH (child)-[:INHERITS_FROM]->(c)
        RETURN c, collect(distinct method.name) as methods,
               collect(distinct parent.name) as parents,
               collect(distinct child.name) as subclasses
        """
        
        result = await neo4j_service.execute_query(query, {"name": name})
        
        if not result:
            return ToolResult(success=False, error=f"Class not found: {name}")
        
        record = result[0]  # This is a DICT from Neo4j
        if isinstance(record, dict):
            cls = record.get("c")
        else:
            cls = record["c"]

        if not cls:
            return ToolResult(success=False, error=f"Class not found: {name}")
        
        logger.info(f"Class analyzed: {name}")
        
        return ToolResult(
            success=True,
            data={
                "name": cls.get("name"),
                "docstring": cls.get("docstring", ""),
                "methods": record["methods"] or [],
                "parents": record["parents"] or [],
                "subclasses": record["subclasses"] or [],
                "line_count": cls.get("line_count", 0)
            }
        )
        
    except Exception as e:
        logger.error(f"Failed to analyze class: {e}")
        return ToolResult(success=False, error=str(e))
