"""Mermaid diagram generation handler - creates diagrams from Neo4j query results."""

from typing import Any, Dict, List

from ....shared.mcp_server import ToolResult
from ....shared.logger import get_logger

logger = get_logger(__name__)


async def generate_mermaid(
    query_results: List[Dict[str, Any]],
    entity_name: str,
    entity_type: str
) -> ToolResult:
    """
    Generate Mermaid diagram from Neo4j query results.
    
    Args:
        query_results: List of query result dictionaries from Neo4j
        entity_name: Central entity name (e.g., "FastAPI")
        entity_type: Entity type (e.g., "Class", "Function")
        
    Returns:
        ToolResult with mermaid_code
    """
    try:
        logger.debug(f"📊 Generating Mermaid diagram for {entity_type}: {entity_name}")
        
        nodes = {entity_name}
        edges = []
        
        # Extract nodes and edges from query results
        for result in query_results:
            if not isinstance(result, dict):
                continue
            
            # Look for source/target patterns in results
            source = result.get("source") or result.get("source_name")
            target = result.get("target") or result.get("target_name")
            rel_type = result.get("relationship_type") or result.get("type", "RELATED")
            
            if source and target:
                nodes.add(source)
                nodes.add(target)
                edges.append(f'    {source} -->|{rel_type}| {target}')
        
        # Build Mermaid diagram
        mermaid_lines = ["graph TD"]
        
        # Add edges (limit to 20 to avoid overcrowding)
        for edge in edges[:20]:
            mermaid_lines.append(edge)
        
        mermaid_code = "\n".join(mermaid_lines)
        
        logger.debug(f"✅ Mermaid diagram generated: {len(nodes)} nodes, {len(edges)} edges")
        
        return ToolResult(
            success=True,
            data={
                "mermaid_code": mermaid_code,
                "nodes_count": len(nodes),
                "edges_count": len(edges)
            }
        )
        
    except Exception as e:
        logger.error(f"❌ Failed to generate mermaid diagram: {e}")
        return ToolResult(success=False, error=str(e))