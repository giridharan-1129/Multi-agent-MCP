"""
AST parsing utilities for indexer service.

Handles entity extraction and relationship building.
"""

from typing import Dict, List, Any
from ....shared.ast_parser import ASTParser
from ....shared.relationship_builder import RelationshipBuilder
from ....shared.logger import get_logger

logger = get_logger(__name__)


async def parse_and_extract_entities(
    file_path: str,
    content: str,
    ast_parser: ASTParser
) -> tuple:
    """
    Parse file and extract entities + relationships.
    
    Returns: (entities_list, imports_set, relationships_list)
    """
    try:
        # Parse AST
        entities = ast_parser.parse_file(file_path)
        
        # Extract imports
        imports = ast_parser.extract_imports(entities)
        
        # Build relationships
        relationship_builder = RelationshipBuilder()
        relationships = relationship_builder.build_relationships(entities, imports, content)
        
        return entities, imports, relationships
    except Exception as e:
        logger.error(f"Failed to parse and extract: {e}")
        raise


def count_entity_types(entities: List[Dict[str, Any]]) -> Dict[str, int]:
    """Count entities by type."""
    counts = {
        "classes": sum(1 for e in entities if e["type"] == "Class"),
        "functions": sum(1 for e in entities if e["type"] == "Function"),
        "methods": sum(1 for e in entities if e["type"] == "Method"),
        "parameters": sum(1 for e in entities if e["type"] == "Parameter"),
        "types": sum(1 for e in entities if e["type"] == "Type"),
        "docstrings": sum(1 for e in entities if e["type"] == "Docstring"),
    }
    return counts
