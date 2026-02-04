"""Handler for code snippet extraction and comparison."""

from ....shared.mcp_server import ToolResult

from ....shared.neo4j_service import Neo4jService
from ....shared.logger import get_logger

logger = get_logger(__name__)


async def get_code_snippet_handler(
    neo4j_service: Neo4jService,
    entity_name: str,
    context_lines: int = 5
) -> ToolResult:
    """Extract code snippet with context."""
    try:
        query = """
        MATCH (e {name: $name})
        RETURN e.source_code as code, e.file_path as file,
               e.start_line as start_line, e.end_line as end_line
        """
        
        result = await neo4j_service.execute_query(query, {"name": entity_name})
        
        if not result:
            return ToolResult(success=False, error=f"Entity not found: {entity_name}")
        
        record = result[0]
        
        logger.info(f"Code snippet extracted: {entity_name}")
        
        return ToolResult(
            success=True,
            data={
                "entity": entity_name,
                "code": record[0] or "",
                "file": record[1] or "",
                "start_line": record[2] or 0,
                "end_line": record[3] or 0
            }
        )
    except Exception as e:
        logger.error(f"Failed to get code snippet: {e}")
        return ToolResult(success=False, error=str(e))


async def compare_implementations_handler(
    neo4j_service: Neo4jService,
    entity1: str,
    entity2: str
) -> ToolResult:
    """Compare two code implementations."""
    try:
        query = """
        MATCH (e1 {name: $entity1})
        MATCH (e2 {name: $entity2})
        RETURN e1.name as name1, e1.source_code as code1,
               e2.name as name2, e2.source_code as code2,
               labels(e1)[0] as type1, labels(e2)[0] as type2
        """
        
        result = await neo4j_service.execute_query(
            query,
            {"entity1": entity1, "entity2": entity2}
        )
        
        if not result:
            return ToolResult(success=False, error="One or both entities not found")
        
        record = result[0]
        
        logger.info(f"Implementations compared: {entity1} vs {entity2}")
        
        return ToolResult(
            success=True,
            data={
                "entity1": {
                    "name": record[0],
                    "code": record[1] or "",
                    "type": record[4]
                },
                "entity2": {
                    "name": record[2],
                    "code": record[3] or "",
                    "type": record[5]
                }
            }
        )
    except Exception as e:
        logger.error(f"Failed to compare implementations: {e}")
        return ToolResult(success=False, error=str(e))


async def explain_implementation_handler(
    neo4j_service: Neo4jService,
    entity_name: str
) -> ToolResult:
    """Generate explanation of code implementation."""
    try:
        query = """
        MATCH (e {name: $name})
        OPTIONAL MATCH (e)-[:CALLS]->(called)
        OPTIONAL MATCH (e)-[:DEPENDS_ON]->(dep)
        RETURN e.docstring as docstring, e.source_code as code,
               collect(distinct called.name) as calls,
               collect(distinct dep.name) as dependencies
        """
        
        result = await neo4j_service.execute_query(query, {"name": entity_name})
        
        if not result:
            return ToolResult(success=False, error=f"Entity not found: {entity_name}")
        
        record = result[0]
        
        explanation = f"""
# {entity_name}

## Documentation
{record[0] or "No documentation available"}

## Implementation
{record[1] or "No source code available"}

## Dependencies
- Calls: {', '.join(record[2]) if record[2] else 'None'}
- Depends on: {', '.join(record[3]) if record[3] else 'None'}
        """
        
        logger.info(f"Implementation explained: {entity_name}")
        
        return ToolResult(
            success=True,
            data={
                "entity": entity_name,
                "explanation": explanation.strip()
            }
        )
    except Exception as e:
        logger.error(f"Failed to explain implementation: {e}")
        return ToolResult(success=False, error=str(e))
