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
        relationships.extend(self._build_docstring_relationships(entities))
        relationships.extend(self._build_method_relationships(entities))
        relationships.extend(self._build_parameter_relationships(entities))
        relationships.extend(self._build_return_relationships(entities))

        logger.info(
            "Relationships built",
            total=len(relationships),
            inheritance=len([r for r in relationships if r["type"] == "INHERITS_FROM"]),
            imports=len([r for r in relationships if r["type"] == "IMPORTS"]),
        )
        # Build class → function CONTAINS relationships
        for entity in entities:
            if entity["type"] == "Function" and entity.get("parent_class"):
                relationships.append({
                    "source": entity["parent_class"],
                    "target": entity["name"],
                    "type": "CONTAINS",
                    "source_module": entity.get("module"),
                    "target_module": entity.get("module"),
                })

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

        source_pkg = entities[0].get("package")
        if not source_pkg:
            return relationships

        for import_module in imports:
            # Only keep internal fastapi imports
            if not import_module.startswith("fastapi"):
                continue

            relationships.append({
                "source": source_pkg,
                "target": import_module,
                "type": "IMPORTS",
            })

        return relationships


    def _build_method_relationships(self, entities):
        relationships = []

        for e in entities:
            if e["type"] == "Method" and e.get("parent_class"):
                relationships.append({
                    "source": e["parent_class"],
                    "target": e["name"],
                    "type": "HAS_METHOD",
                    "source_module": e["module"],
                    "target_module": e["module"],
                })

        return relationships

    def _build_parameter_relationships(self, entities):
        relationships = []

        for e in entities:
            if e["type"] == "Parameter":
                relationships.append({
                    "source": e["function"],
                    "target": e["name"],
                    "type": "HAS_PARAM",
                })

        return relationships


    def _build_return_relationships(self, entities):
        relationships = []

        for e in entities:
            if e["type"] == "Type":
                relationships.append({
                    "source": e["function"],
                    "target": e["name"],
                    "type": "RETURNS",
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

    def _resolve_call_target(self, call_name, entity_index):
        """
        Resolve a call name to Function or Method entity.
        Priority:
        1. Method
        2. Function
        """
        if (call_name, "Method") in entity_index:
            return call_name, "Method"

        if (call_name, "Function") in entity_index:
            return call_name, "Function"

        return None, None

    def _build_call_relationships_from_entities(self, entities):
        relationships = []

        # Index functions
        function_index = {
            e["name"]: e
            for e in entities
            if e["type"] == "Function"
        }

        # Index methods by (class, method)
        method_index = {}
        for e in entities:
            if e["type"] == "Method" and e.get("parent_class"):
                method_index[(e["parent_class"], e["name"])] = e

        for caller in entities:
            if caller["type"] not in {"Function", "Method"}:
                continue

            instance_map = caller.get("instance_map", {})

            for call in caller.get("calls", []):

                # -------------------------
                # METHOD CALL (obj.method)
                # -------------------------
                if call["type"] == "method":
                    obj = call["object"]
                    method_name = call["name"]

                    class_name = instance_map.get(obj)
                    if not class_name:
                        continue

                    target = method_index.get((class_name, method_name))
                    if not target:
                        continue

                    relationships.append({
                        "source": caller["name"],
                        "source_module": caller.get("module"),
                        "target": target["name"],
                        "target_module": target.get("module"),
                        "type": "CALLS",
                        "line_number": caller.get("line_number"),
                    })

                # -------------------------
                # FUNCTION CALL (foo())
                # -------------------------
                elif call["type"] == "function":
                    target = function_index.get(call["name"])
                    if not target:
                        continue

                    relationships.append({
                        "source": caller["name"],
                        "source_module": caller.get("module"),
                        "target": target["name"],
                        "target_module": target.get("module"),
                        "type": "CALLS",
                        "line_number": caller.get("line_number"),
                    })

        return relationships



    def _build_docstring_relationships(
        self,
        entities: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        relationships = []

        # Index docstrings by (module, scope, entity name)
        docstring_index = {}

        for e in entities:
            if e["type"] == "Docstring" and e["scope"] in {"class", "function"}:
                parts = e["name"].split("::")
                if len(parts) >= 3:
                    entity_name = parts[-2]
                    key = (e["module"], e["scope"], entity_name)
                    docstring_index[key] = e

        for entity in entities:
            if entity["type"] not in {"Class", "Function", "Method"}:
                continue

            scope = entity["type"].lower()
            key = (entity["module"], scope, entity["name"])

            doc = docstring_index.get(key)
            if not doc:
                continue

            relationships.append({
                "source": entity["name"],
                "source_module": entity["module"],
                "target": doc["name"],
                "target_module": doc["module"],
                "type": "DOCUMENTED_BY",
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
