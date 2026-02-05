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
        OPTIONAL MATCH (e)<-[:DEFINES]-(f:File)
        RETURN e.name as entity_name, e.docstring as code, f.path as file,
               e.line_number as start_line, e.line_number as end_line
        """
        
        result = await neo4j_service.execute_query(query, {"name": entity_name})
        
        if not result:
            return ToolResult(success=False, error=f"Entity not found: {entity_name}")
        record = result[0]  # Dict with keys: {"code": ..., "file": ..., "start_line": ..., "end_line": ...}
        
        logger.info(f"Code snippet extracted: {entity_name}")
        
        return ToolResult(
            success=True,
            data={
                "entity": entity_name,
                "code": record["code"] or "",
                "file": record["file"] or "",
                "start_line": record["start_line"] or 0,
                "end_line": record["end_line"] or 0
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
        OPTIONAL MATCH (e1)<-[:DEFINES]-(f1:File)
        OPTIONAL MATCH (e2)<-[:DEFINES]-(f2:File)
        RETURN e1.name as name1, e1.docstring as code1,
               e2.name as name2, e2.docstring as code2,
               labels(e1)[0] as type1, labels(e2)[0] as type2
        """
        
        result = await neo4j_service.execute_query(
            query,
            {"entity1": entity1, "entity2": entity2}
        )
        
        if not result:
            return ToolResult(success=False, error="One or both entities not found")
        
        record = result[0]  # Dict with keys: {"name1": ..., "code1": ..., "name2": ..., "code2": ..., "type1": ..., "type2": ...}
        
        logger.info(f"Implementations compared: {entity1} vs {entity2}")
        
        return ToolResult(
            success=True,
            data={
                "entity1": {
                    "name": record["name1"],
                    "code": record["code1"] or "",
                    "type": record["type1"]
                },
                "entity2": {
                    "name": record["name2"],
                    "code": record["code2"] or "",
                    "type": record["type2"]
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
        OPTIONAL MATCH (e)-[r]->(dep)
        WHERE type(r) IN ['CALLS', 'INHERITS_FROM', 'CONTAINS', 'IMPORTS']
        RETURN e.docstring as docstring, e.docstring as code,
               collect(distinct called.name) as calls,
               collect(distinct dep.name) as dependencies
        """
        
        result = await neo4j_service.execute_query(query, {"name": entity_name})
        
        if not result:
            return ToolResult(success=False, error=f"Entity not found: {entity_name}")
        
        record = result[0]  # Dict with keys: {"docstring": ..., "code": ..., "calls": [...], "dependencies": [...]}
        
        explanation = f"""
# {entity_name}

## Documentation
{record["docstring"] or "No documentation available"}

## Implementation
{record["code"] or "No source code available"}

## Dependencies
- Calls: {', '.join(record["calls"]) if record["calls"] else 'None'}
- Depends on: {', '.join(record["dependencies"]) if record["dependencies"] else 'None'}
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
