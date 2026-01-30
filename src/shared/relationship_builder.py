"""
Relationship Builder Service.

WHAT: Analyze code entities and build relationships between them
WHY: Create the knowledge graph edges (dependencies, inheritance, calls)
HOW: Parse imports, decorators, type hints to find relationships

Example:
    builder = RelationshipBuilder()
    relationships = builder.build_relationships(entities, imports)
    # Returns: [
    #     {"source": "FastAPI", "target": "Starlette", "type": "INHERITS_FROM"},
    #     {"source": "APIRouter", "target": "routing", "type": "IMPORTS"},
    # ]
"""

import re
from typing import Any, Dict, List, Optional, Set

from .logger import get_logger

logger = get_logger(__name__)


class RelationshipBuilder:
    """
    Build relationships between code entities.

    Analyzes dependencies, inheritance, function calls, and decorators
    to create relationships in the knowledge graph.
    """

    def __init__(self):
        """Initialize relationship builder."""
        logger.debug("RelationshipBuilder initialized")

    def build_relationships(
        self,
        entities: List[Dict[str, Any]],
        imports: Set[str],
        file_content: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        Build relationships between entities.

        Args:
            entities: List of parsed entities (classes, functions)
            imports: Set of imported modules
            file_content: Original file content for deeper analysis

        Returns:
            List of relationships
        """
        relationships = []

        # Build inheritance relationships
        entity_lookup = {
            (e["name"], e["type"]): e.get("module")
            for e in entities
        }

        relationships.extend(
            self._build_inheritance_relationships(entities, entity_lookup)
        )

        # Build import relationships
        relationships.extend(self._build_import_relationships(entities, imports))

        # Build decorator relationships
        relationships.extend(self._build_decorator_relationships(entities))

        # Build call relationships
        relationships.extend(self._build_call_relationships_from_entities(entities))

        logger.info(
            "Relationships built",
            total=len(relationships),
            inheritance=len([r for r in relationships if r["type"] == "INHERITS_FROM"]),
            imports=len([r for r in relationships if r["type"] == "IMPORTS"]),
        )

        return relationships

    def _build_inheritance_relationships(
        self,
        entities: List[Dict[str, Any]],
        entity_lookup: Dict[tuple, str],
    ):
        """
        Build inheritance relationships.

        Args:
            entities: List of entities

        Returns:
            List of inheritance relationships
        """
        relationships = []

        for entity in entities:
            if entity["type"] == "Class" and entity.get("bases"):
                for base in entity["bases"]:
                    # Extract class name from base (handles Module.ClassName)
                    class_name = base.split(".")[-1] if "." in base else base

                    relationship = {
                            "source": entity["name"],
                            "source_module": entity.get("module"),
                            "target": class_name,
                            "target_module": (
                                entity_lookup.get((class_name, "Class"))
                            ),
                            "type": "INHERITS_FROM",
                            "line_number": entity.get("line_number"),
                        }

                    relationships.append(relationship)

                    logger.debug(
                        "Inheritance relationship found",
                        source=entity["name"],
                        target=class_name,
                    )

        return relationships

    def _build_import_relationships(self, entities, imports):
        relationships = []

        if not entities or not imports:
            return relationships

        source_pkg = entities[0].get("package", "").split(".")[0]
        if not source_pkg:
            return relationships

        for import_module in imports:
            target_pkg = import_module.split(".")[0]

            relationships.append({
                "source": source_pkg,
                "target": target_pkg,
                "type": "IMPORTS",
            })

        return relationships





    def _build_decorator_relationships(
        self,
        entities: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """
        Build decorator relationships.

        Args:
            entities: List of entities

        Returns:
            List of decorator relationships
        """
        relationships = []

        for entity in entities:
            if entity.get("decorators"):
                for decorator in entity["decorators"]:
                    # Extract decorator name (handles @decorator.subdecorator)
                    decorator_name = decorator.split("(")[0]  # Remove parameters
                    decorator_name = decorator_name.split(".")[-1]  # Get last part

                    relationship = {
                        "source": entity["name"],
                        "source_module": entity.get("module"),
                        "target": decorator_name,
                        "target_module": entity.get("module"),  # decorators usually local
                        "type": "DECORATED_BY",
                        "decorator_full": decorator,
                        "line_number": entity.get("line_number"),
                    }

                    relationships.append(relationship)

                    logger.debug(
                        "Decorator relationship found",
                        source=entity["name"],
                        decorator=decorator,
                    )

        return relationships

    def _build_call_relationships_from_entities(
        self,
        entities: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        relationships = []

        functions = {
            e["name"]: e
            for e in entities
            if e["type"] == "Function"
        }

        for func in entities:
            if func["type"] != "Function":
                continue

            for called_name in func.get("calls", []):
                target = functions.get(called_name)
                if not target:
                    continue

                relationships.append({
                    "source": func["name"],
                    "source_module": func.get("module"),
                    "target": target["name"],
                    "target_module": target.get("module"),
                    "type": "CALLS",
                    "line_number": func.get("line_number"),
                })

        return relationships


    def find_circular_dependencies(
        self,
        relationships: List[Dict[str, Any]],
    ) -> List[List[str]]:
        """
        Find circular dependencies in relationships.

        Args:
            relationships: List of relationships

        Returns:
            List of circular dependency chains
        """
        # Build adjacency list
        graph: Dict[str, Set[str]] = {}

        for rel in relationships:
            if rel["type"] in {"IMPORTS", "INHERITS_FROM"}:
                source = rel["source"]
                target = rel["target"]

                if source not in graph:
                    graph[source] = set()
                graph[source].add(target)

        # Find cycles using DFS
        cycles = []
        visited: Set[str] = set()
        rec_stack: Set[str] = set()

        def dfs(node: str, path: List[str]) -> None:
            visited.add(node)
            rec_stack.add(node)
            path.append(node)

            if node in graph:
                for neighbor in graph[node]:
                    if neighbor not in visited:
                        dfs(neighbor, path[:])
                    elif neighbor in rec_stack:
                        # Found a cycle
                        cycle_start = path.index(neighbor)
                        cycle = path[cycle_start:] + [neighbor]
                        if cycle not in cycles:
                            cycles.append(cycle)

            rec_stack.remove(node)

        for node in graph:
            if node not in visited:
                dfs(node, [])

        if cycles:
            logger.warning("Circular dependencies found", cycles=cycles)

        return cycles

    def analyze_dependency_depth(
        self,
        relationships: List[Dict[str, Any]],
        entity_name: str,
    ) -> Dict[str, Any]:
        """
        Analyze dependency depth for an entity.

        Shows how deep the dependency chain goes.

        Args:
            relationships: List of relationships
            entity_name: Entity to analyze

        Returns:
            Dictionary with depth analysis
        """
        # Build graph
        graph: Dict[str, Set[str]] = {}
        for rel in relationships:
            source = rel["source"]
            target = rel["target"]
            if source not in graph:
                graph[source] = set()
            graph[source].add(target)

        # BFS to find depth
        visited = {entity_name}
        queue = [(entity_name, 0)]
        max_depth = 0
        all_dependencies = set()

        while queue:
            node, depth = queue.pop(0)
            max_depth = max(max_depth, depth)

            if node in graph:
                for neighbor in graph[node]:
                    all_dependencies.add(neighbor)
                    if neighbor not in visited:
                        visited.add(neighbor)
                        queue.append((neighbor, depth + 1))

        analysis = {
            "entity": entity_name,
            "max_depth": max_depth,
            "total_dependencies": len(all_dependencies),
            "direct_dependencies": len(graph.get(entity_name, set())),
            "all_dependencies": list(all_dependencies),
        }

        logger.info("Dependency depth analyzed", entity=entity_name, depth=max_depth)
        return analysis

    def find_unused_imports(
        self,
        imports: Set[str],
        entities: List[Dict[str, Any]],
        file_content: str,
    ) -> List[str]:
        """
        Find unused imports in file.

        Args:
            imports: Set of imported modules
            entities: List of entities in file
            file_content: File content

        Returns:
            List of unused imports
        """
        unused = []

        for import_name in imports:
            # Check if import is used in any entity
            used = False

            # Check in docstrings
            for entity in entities:
                if entity.get("docstring") and import_name in entity["docstring"]:
                    used = True
                    break

            # Check in file content
            if not used and import_name in file_content:
                used = True

            if not used:
                unused.append(import_name)
                logger.debug("Unused import found", import_name=import_name)

        logger.info("Unused imports analysis", unused_count=len(unused))
        return unused


# Global relationship builder instance
relationship_builder: Optional[RelationshipBuilder] = None


def init_relationship_builder() -> RelationshipBuilder:
    """
    Initialize relationship builder.

    Returns:
        RelationshipBuilder instance
    """
    global relationship_builder
    relationship_builder = RelationshipBuilder()
    return relationship_builder


def get_relationship_builder() -> RelationshipBuilder:
    """
    Get initialized relationship builder.

    Returns:
        RelationshipBuilder instance
    """
    global relationship_builder
    if not relationship_builder:
        relationship_builder = RelationshipBuilder()
    return relationship_builder
