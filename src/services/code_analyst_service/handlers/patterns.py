"""Handler for design pattern detection."""

from typing import Optional
from ....shared.mcp_server import ToolResult

from ....shared.neo4j_service import Neo4jService
from ....shared.logger import get_logger

logger = get_logger(__name__)


async def find_patterns_handler(
    neo4j_service: Neo4jService,
    pattern_type: Optional[str] = None
) -> ToolResult:
    """Find design patterns in codebase."""
    try:
        if pattern_type:
            query = """
            MATCH (e {design_pattern: $pattern})
            RETURN e.name as name, e.design_pattern as pattern,
                   labels(e)[0] as type
            LIMIT 20
            """
            params = {"pattern": pattern_type}
        else:
            query = """
            MATCH (e)
            WHERE e.design_pattern IS NOT NULL
            RETURN e.name as name, e.design_pattern as pattern,
                   labels(e)[0] as type
            LIMIT 20
            """
            params = {}
        
        result = await neo4j_service.execute_query(query, params)
        
        patterns = [
            {"name": record["name"], "pattern": record["pattern"], "type": record["type"]}
            for record in result
        ]
        
        logger.info(f"Patterns found: {len(patterns)}")
        
        return ToolResult(
            success=True,
            data={
                "pattern_type": pattern_type,
                "found_patterns": patterns,
                "count": len(patterns)
            }
        )
    except Exception as e:
        logger.error(f"Failed to find patterns: {e}")
        return ToolResult(success=False, error=str(e))
