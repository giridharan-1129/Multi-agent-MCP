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
    """Generate explanation of code implementation with full details."""
    try:
        # Query to get entity details with relationships
        query = """
        MATCH (e) WHERE toLower(e.name) = toLower($name)
        OPTIONAL MATCH (e)-[:CALLS]->(called:Function)
        OPTIONAL MATCH (caller:Function)-[:CALLS]->(e)
        OPTIONAL MATCH (e)-[:IMPORTS]->(imp)
        OPTIONAL MATCH (e)-[:INHERITS_FROM]->(parent)
        OPTIONAL MATCH (child)-[:INHERITS_FROM]->(e)
        RETURN 
            e.name as entity_name,
            labels(e)[0] as entity_type,
            e.docstring as docstring,
            e.module as module,
            e.line_number as line_number,
            collect(distinct called.name) as calls,
            collect(distinct caller.name) as called_by,
            collect(distinct imp.name) as imports,
            collect(distinct parent.name) as parent_class,
            collect(distinct child.name) as child_classes
        """
        
        result = await neo4j_service.execute_query(query, {"name": entity_name})
        
        if not result:
            return ToolResult(success=False, error=f"Entity not found: {entity_name}")
        
        record = result[0]
        # Now record is a dict with flattened keys, not nested entity_data
        if not isinstance(record, dict) or not record.get("entity_name"):
            return ToolResult(success=False, error=f"Entity not found: {entity_name}")
        
        data = record  # Use the record directly now
        
        # Build comprehensive explanation
        entity_type = data.get("entity_type", "Unknown")
        docstring = data.get("docstring", "No documentation")
        module = data.get("module", "N/A")
        line_num = data.get("line_number", "N/A")
        calls = [c for c in data.get("calls", []) if c]
        called_by = [c for c in data.get("called_by", []) if c]
        imports = [i for i in data.get("imports", []) if i]
        parents = [p for p in data.get("parent_class", []) if p]
        children = [c for c in data.get("child_classes", []) if c]
        
        explanation = f"""
**{entity_name}** (`{entity_type}`)
- **Location:** `{module}:{line_num}`
- **Type:** {entity_type}

**What it does:**
{docstring}

**Calls (Functions/Methods it invokes):** {len(calls)} total
{chr(10).join(f"  • {c}" for c in calls[:10]) if calls else "  • None"}
{f"  ... and {len(calls) - 10} more" if len(calls) > 10 else ""}

**Called by (Who uses it):** {len(called_by)} components
{chr(10).join(f"  • {c}" for c in called_by[:10]) if called_by else "  • None"}
{f"  ... and {len(called_by) - 10} more" if len(called_by) > 10 else ""}

**Imports:** {len(imports)} dependencies
{chr(10).join(f"  • {i}" for i in imports[:5]) if imports else "  • None"}
{f"  ... and {len(imports) - 5} more" if len(imports) > 5 else ""}

**Inheritance:**
{f"Inherits from: {', '.join(parents)}" if parents else "No parent class"}
{f"Subclasses: {', '.join(children)}" if children else "No subclasses"}
        """
        
        logger.info(f"Implementation explained: {entity_name}")
        
        return ToolResult(
            success=True,
            data={
                "entity_name": entity_name,
                "entity_type": entity_type,
                "module": module,
                "line_number": line_num,
                "explanation": explanation.strip(),
                "calls_count": len(calls),
                "called_by_count": len(called_by),
                "imports_count": len(imports)
            }
        )
    except Exception as e:
        logger.error(f"Failed to explain implementation: {e}")
        return ToolResult(success=False, error=str(e))