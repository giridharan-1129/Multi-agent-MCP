"""Handler for function analysis."""

from ....shared.mcp_server import ToolResult

from ....shared.neo4j_service import Neo4jService
from ....shared.logger import get_logger

logger = get_logger(__name__)


async def analyze_function_handler(
    neo4j_service: Neo4jService,
    name: str
) -> ToolResult:
    """Analyze function implementation and calls."""
    try:
        query = """
        MATCH (f:Function {name: $name})
        OPTIONAL MATCH (f)-[:CALLS]->(called)
        OPTIONAL MATCH (caller)-[:CALLS]->(f)
        OPTIONAL MATCH (f)-[:HAS_PARAM]->(param)
        RETURN f, collect(distinct called.name) as calls, 
               collect(distinct caller.name) as callers,
               collect(distinct param.name) as parameters
        """
        
        result = await neo4j_service.execute_query(query, {"name": name})
        
        if not result:
            return ToolResult(success=False, error=f"Function not found: {name}")
        
        record = result[0]  # This is a DICT from Neo4j
        if isinstance(record, dict):
            func = record.get("f")
        else:
            func = record["f"]

        if not func:
            return ToolResult(success=False, error=f"Function not found: {name}")
        
        logger.info(f"Function analyzed: {name}")
        
        return ToolResult(
            success=True,
            data={
                "name": func.get("name"),
                "docstring": func.get("docstring", ""),
                "calls": record["calls"] or [],
                "callers": record["callers"] or [],
                "parameters": record["parameters"] or [],
                "complexity": func.get("complexity", "unknown"),
                "line_count": func.get("line_count", 0)
            }
        )
    except Exception as e:
        logger.error(f"Failed to analyze function: {e}")
        return ToolResult(success=False, error=str(e))
