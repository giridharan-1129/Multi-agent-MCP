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

    def _extract_module_from_file(self, file_path: str) -> Optional[str]:
        """Extract module name from file path."""
        if not file_path:
            return None
        
        parts = file_path.replace("\\", "/").split("/")
        
        if "fastapi" not in parts:
            return None
        
        try:
            idx = len(parts) - 1 - parts[::-1].index("fastapi")
            module_parts = parts[idx:-1]
            filename = parts[-1].replace(".py", "")
            
            if filename != "__init__":
                module_parts.append(filename)
            
            return ".".join(module_parts) if module_parts else None
        except Exception:
            return None    

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

        relationships.extend(self._build_import_relationships(entities, imports))


        # Build call relationships
        relationships.extend(self._build_call_relationships_from_entities(entities))
        relationships.extend(self._build_docstring_relationships(entities))
        relationships.extend(self._build_method_relationships(entities))
        relationships.extend(self._build_parameter_relationships(entities))
        relationships.extend(self._build_decorated_relationships(entities))
        relationships.extend(self._build_depends_on_relationships(entities))

        logger.info(
            "Relationships built",
            total=len(relationships),
            inheritance=len([r for r in relationships if r["type"] == "INHERITS_FROM"]),
            imports=len([r for r in relationships if r["type"] == "IMPORTS"]),
        )
        # Build CONTAINS relationships: Module→Class and Class→Function
        for entity in entities:
            # Module CONTAINS Class
            if entity["type"] == "Class":
                module_name = self._extract_module_from_file(entity.get("module"))
                if module_name:
                    relationships.append({
                        "source": module_name,
                        "source_module": entity.get("module"),
                        "target": entity["name"],
                        "target_module": entity.get("module"),
                        "type": "CONTAINS",
                        "line_number": entity.get("line_number"),
                    })
            
            # Class CONTAINS Function/Method
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
        Build inheritance relationships - for both internal and external classes.
        """
        relationships = []

        for entity in entities:
            if entity["type"] == "Class" and entity.get("bases"):
                for base in entity["bases"]:
                    class_name = base.split(".")[-1] if "." in base else base
                    target_module = entity_lookup.get((class_name, "Class"))
                    
                    # ✅ Create relationship EVEN IF external (e.g., Exception from builtins)
                    relationship = {
                        "source": entity["name"],
                        "source_module": entity.get("module"),
                        "target": class_name,
                        "target_module": target_module if target_module else "builtins",
                        "type": "INHERITS_FROM",
                        "line_number": entity.get("line_number"),
                    }
                    relationships.append(relationship)

                    logger.debug(
                        "Inheritance relationship found",
                        source=entity["name"],
                        target=class_name,
                        is_external=target_module is None,
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
                    "type": "HAS_PARAMETER",  # ✅ CORRECT NAME
                })

        return relationships

    def _build_decorated_relationships(self, entities):
        """Build DECORATED_BY relationships between functions/classes and decorators."""
        relationships = []

        for entity in entities:
            if entity["type"] in {"Function", "Method", "Class"}:
                decorators = entity.get("decorators", [])
                
                if decorators:
                    for decorator in decorators:
                        relationships.append({
                            "source": entity["name"],
                            "source_module": entity.get("module"),
                            "target": decorator,
                            "target_module": entity.get("module"),
                            "type": "DECORATED_BY",
                            "line_number": entity.get("line_number"),
                        })

        return relationships

    def _build_depends_on_relationships(self, entities):
        """Build DEPENDS_ON relationships between classes that have dependencies."""
        relationships = []

        for entity in entities:
            if entity["type"] == "Class" and entity.get("bases"):
                    # Class depends on its base classes
                    for base in entity["bases"]:
                        class_name = base.split(".")[-1] if "." in base else base
                        
                        relationships.append({
                            "source": entity["name"],
                            "source_module": entity.get("module"),
                            "target": class_name,
                            "target_module": entity.get("module"),
                            "type": "DEPENDS_ON",
                            "line_number": entity.get("line_number"),
                        })

        return relationships

    def _build_call_relationships_from_entities(self, entities):
        relationships = []

        # ✅ CREATE COMPREHENSIVE INDEXES
        # Index ALL functions and methods by name (not just in module)
        function_index = {}  # name -> entity
        method_index = {}    # name -> entity (any class)
        class_index = {}     # name -> entity
        
        for e in entities:
            if e["type"] == "Function":
                function_index[e["name"]] = e
            elif e["type"] == "Method":
                method_index[e["name"]] = e
            elif e["type"] == "Class":
                class_index[e["name"]] = e

        # ✅ PROCESS ALL CALLERS
        for caller in entities:
            if caller["type"] not in {"Function", "Method"}:
                continue

            instance_map = caller.get("instance_map", {})
            calls = caller.get("calls", [])
            
            if not calls:
                continue

            for call in calls:
                # ✅ DIRECT FUNCTION CALL: foo()
                if call["type"] == "function":
                    call_name = call.get("name")
                    
                    # First: Look in function index
                    if call_name in function_index:
                        target = function_index[call_name]
                        relationships.append({
                            "source": caller["name"],
                            "source_module": caller.get("module"),
                            "target": target["name"],
                            "target_module": target.get("module"),
                            "type": "CALLS",
                            "line_number": caller.get("line_number"),
                        })
                    # Second: Look in method index (class methods called directly)
                    elif call_name in method_index:
                        target = method_index[call_name]
                        relationships.append({
                            "source": caller["name"],
                            "source_module": caller.get("module"),
                            "target": target["name"],
                            "target_module": target.get("module"),
                            "type": "CALLS",
                            "line_number": caller.get("line_number"),
                        })

                # ✅ METHOD CALL: obj.method() or self.method()
                elif call["type"] == "method":
                    obj_name = call.get("object")
                    method_name = call.get("name")
                    
                    # Resolve object to class
                    class_name = instance_map.get(obj_name)
                    
                    if not class_name:
                        # Fallback: Try direct method lookup
                        if method_name in method_index:
                            target = method_index[method_name]
                            relationships.append({
                                "source": caller["name"],
                                "source_module": caller.get("module"),
                                "target": target["name"],
                                "target_module": target.get("module"),
                                "type": "CALLS",
                                "line_number": caller.get("line_number"),
                            })
                        continue
                    
                    # Look up method in that class
                    if method_name in method_index:
                        target = method_index[method_name]
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
