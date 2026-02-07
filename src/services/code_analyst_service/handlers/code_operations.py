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
        # Query to get entity details with relationships (improved: supports ALL relationship types and node types)
        query = """
        MATCH (e) WHERE toLower(e.name) = toLower($name)
        
        // Outgoing relationships - what this entity USES/CALLS/IMPORTS
        OPTIONAL MATCH (e)-[rel_out:CALLS|IMPORTS|USES|DEPENDS_ON]->(outgoing)
        
        // Incoming relationships - what USES/CALLS this entity
        OPTIONAL MATCH (incoming)-[rel_in:CALLS|IMPORTS|USES|DEPENDS_ON]->(e)
        
        // Inheritance outgoing - what this entity inherits FROM
        OPTIONAL MATCH (e)-[:INHERITS_FROM]->(parent)
        
        // Inheritance incoming - what inherits FROM this entity
        OPTIONAL MATCH (child)-[:INHERITS_FROM]->(e)
        
        RETURN 
            e.name as entity_name,
            labels(e)[0] as entity_type,
            e.docstring as docstring,
            e.module as module,
            e.line_number as line_number,
            collect(distinct {name: outgoing.name, type: labels(outgoing)[0], relation: type(rel_out)}) as outgoing_rels,
            collect(distinct {name: incoming.name, type: labels(incoming)[0], relation: type(rel_in)}) as incoming_rels,
            collect(distinct parent.name) as parent_class,
            collect(distinct child.name) as child_classes
        """
        
        logger.info(f"📍 Querying for entity: {entity_name}")
        logger.debug(f"   Using comprehensive relationship query")
        
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
        
        # ✅ FIXED: Extract outgoing and incoming relationships
        outgoing_rels = [r for r in data.get("outgoing_rels", []) if isinstance(r, dict) and r.get("name")]
        incoming_rels = [r for r in data.get("incoming_rels", []) if isinstance(r, dict) and r.get("name")]
        
        parents = [p for p in data.get("parent_class", []) if p]
        children = [c for c in data.get("child_classes", []) if c]
        
        logger.info(f"   Found: {len(outgoing_rels)} outgoing rels, {len(incoming_rels)} incoming rels")
        logger.debug(f"      Outgoing: {[r.get('name') for r in outgoing_rels]}")
        logger.debug(f"      Incoming: {[r.get('name') for r in incoming_rels]}")
        
        # ✅ FIXED: Better formatting with relationship types
        explanation = f"""
**{entity_name}** (`{entity_type}`)
- **Location:** `{module}:{line_num}`
- **Type:** {entity_type}

**What it does:**
{docstring}

**Dependencies (What {entity_name} uses/imports/depends on):** {len(outgoing_rels)} total
{chr(10).join(f"  • {r.get('name')} ({r.get('type')}) via {r.get('relation', 'USES')}" for r in outgoing_rels[:10]) if outgoing_rels else "  • None"}
{f"  ... and {len(outgoing_rels) - 10} more" if len(outgoing_rels) > 10 else ""}

**Dependents (What uses/depends on {entity_name}):** {len(incoming_rels)} components
{chr(10).join(f"  • {r.get('name')} ({r.get('type')}) via {r.get('relation', 'USES')}" for r in incoming_rels[:10]) if incoming_rels else "  • None"}
{f"  ... and {len(incoming_rels) - 10} more" if len(incoming_rels) > 10 else ""}

**Inheritance:**
{f"Inherits from: {', '.join(parents)}" if parents else "No parent class"}
{f"Subclasses: {', '.join(children)}" if children else "No subclasses"}
        """
        
        logger.info(f"✅ Implementation explained: {entity_name}")
        logger.info(f"   - Outgoing: {len(outgoing_rels)}, Incoming: {len(incoming_rels)}")
        
        return ToolResult(
            success=True,
            data={
                "entity_name": entity_name,
                "entity_type": entity_type,
                "module": module,
                "line_number": line_num,
                "explanation": explanation.strip(),
                "calls_count": len(incoming_rels),  # Changed: incoming rels = who calls this
                "called_by_count": len(outgoing_rels),  # Changed: outgoing rels = what this calls
                "imports_count": len(outgoing_rels)  # Same as calls_count
            }
        )
    except Exception as e:
        logger.error(f"Failed to explain implementation: {e}")
        return ToolResult(success=False, error=str(e))