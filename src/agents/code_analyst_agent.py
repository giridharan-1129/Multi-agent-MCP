"""
Code Analyst Agent - MCP Agent for Code Analysis.

WHAT: MCP agent that analyzes code patterns and provides insights
WHY: Explain code, identify patterns, compare implementations, suggest improvements
HOW: Query knowledge graph, analyze AST, use LLM for insights

Example:
    agent = CodeAnalystAgent()
    await agent.startup()
    
    result = await agent.execute_tool("analyze_function", {
        "name": "get_openapi_schema",
        "module": "fastapi/openapi"
    })
"""

from typing import Any, Dict, List, Optional

from ..shared.base_agent import BaseAgent
from ..shared.logger import get_logger
from ..shared.mcp_types import MCPTool, ToolResult, ToolParameter, ToolDefinition
from ..shared.neo4j_service import get_neo4j_service
from ..shared.relationship_builder import get_relationship_builder

logger = get_logger(__name__)


class AnalyzeFunctionTool(MCPTool):
    """Tool to analyze a function."""

    name: str = "analyze_function"
    description: str = "Analyze a function and provide insights"
    category: str = "analysis"

    async def execute(
        self,
        name: str,
        module: Optional[str] = None,
    ) -> ToolResult:
        """
        Analyze a function.

        Args:
            name: Function name
            module: Optional module filter

        Returns:
            ToolResult with analysis
        """
        try:
            neo4j = get_neo4j_service()

            # Find the function
            query = """
            MATCH (f:Function)
            WHERE f.name = $name
            OPTIONAL MATCH (f)<-[r:CALLS]-(caller)
            OPTIONAL MATCH (f)-[r2:CALLS]->(called)
            RETURN f { .* } AS function,
                   collect(distinct caller.name) AS callers,
                   collect(distinct called.name) AS called_functions
            LIMIT 1
            """

            results = await neo4j.execute_query(query, {"name": name})

            if not results:
                suggestion_query = """
                MATCH (f:Function)
                WHERE f.name CONTAINS $name
                RETURN f.name AS name, f.module AS module
                LIMIT 5
                """
                suggestions = await neo4j.execute_query(
                    suggestion_query, {"name": name}
                )

                logger.info("Function not found", name=name)

                return ToolResult(
                    success=False,
                    error=f"Function '{name}' not found",
                    data={
                        "reason": "No matching Function node exists in the indexed repository.",
                        "note": "Tool names and code function names are different concepts.",
                        "suggestions": suggestions or [],
                        "next_action": "Retry with one of the suggested function names."
                    },
                )


            result = results[0]
            function = result["function"]

            callers = result.get("callers", [])
            called_functions = result.get("called_functions", [])

            # --- Semantic analysis (graph + metadata based) ---
            control_flow = {
                "fan_in": len(callers),
                "fan_out": len(called_functions),
                "is_entry_point": len(callers) == 0,
                "is_orchestrator": len(called_functions) >= 3,
            }

            side_effects = {
                "likely_io": any(
                    kw in (function.get("name") or "").lower()
                    for kw in ["read", "write", "load", "save", "fetch", "request"]
                ),
                "likely_db_access": any(
                    kw in (function.get("name") or "").lower()
                    for kw in ["query", "insert", "update", "delete"]
                ),
            }

            # --- Complexity estimation (heuristic, explainable) ---
            if control_flow["is_orchestrator"]:
                estimated_complexity = "O(n) – coordination-heavy"
            elif len(function.get("parameters", [])) > 4:
                estimated_complexity = "O(n) – parameter-heavy"
            else:
                estimated_complexity = "O(1) – simple logic"

            analysis = {
                "name": function.get("name"),
                "module": function.get("module"),
                "docstring": function.get("docstring"),
                "line_number": function.get("line_number"),
                "is_async": function.get("is_async", False),
                "parameters": function.get("parameters", []),
                "returns": function.get("returns"),
                "decorators": function.get("decorators", []),
                "callers": callers,
                "called_functions": called_functions,
                "analysis": {
                    "control_flow": control_flow,
                    "side_effects": side_effects,
                    "estimated_complexity": estimated_complexity,
                },
                "insight": (
                    "This function acts as an orchestration layer coordinating multiple calls."
                    if control_flow["is_orchestrator"]
                    else "This function appears to be a leaf-level implementation."
                ),
            }


            logger.info("Function analyzed", name=name)
            return ToolResult(
                success=True,
                data=analysis,
            )

        except Exception as e:
            logger.error("Failed to analyze function", name=name, error=str(e))
            return ToolResult(
                success=False,
                error=str(e),
            )

    def get_definition(self) -> ToolDefinition:
        """Get tool definition."""
        return ToolDefinition(
            name=self.name,
            description=self.description,
            parameters=[
                ToolParameter(
                    name="name",
                    description="Function name to analyze",
                    type="string",
                    required=True,
                ),
                ToolParameter(
                    name="module",
                    description="Optional module filter",
                    type="string",
                    required=False,
                ),
            ],
            category=self.category,
        )


class AnalyzeClassTool(MCPTool):
    """Tool to analyze a class."""

    name: str = "analyze_class"
    description: str = "Analyze a class and provide insights"
    category: str = "analysis"

    async def execute(
        self,
        name: str,
        module: Optional[str] = None,
    ) -> ToolResult:
        """
        Analyze a class.

        Args:
            name: Class name
            module: Optional module filter

        Returns:
            ToolResult with analysis
        """
        try:
            neo4j = get_neo4j_service()

            # Find the class
            query = """
            MATCH (c:Class)
            WHERE c.name = $name
            OPTIONAL MATCH (c)-[r:INHERITS_FROM]->(parent)
            OPTIONAL MATCH (child)-[r2:INHERITS_FROM]->(c)
            RETURN c { .* } AS class,
                   collect(distinct parent.name) AS parent_classes,
                   collect(distinct child.name) AS child_classes
            LIMIT 1
            """

            results = await neo4j.execute_query(query, {"name": name})

            if not results:
                logger.info("Class not found", name=name)
                return ToolResult(
                    success=False,
                    error=f"Class '{name}' not found",
                )

            result = results[0]
            cls = result["class"]

            analysis = {
                "name": cls.get("name"),
                "module": cls.get("module"),
                "docstring": cls.get("docstring"),
                "line_number": cls.get("line_number"),
                "bases": cls.get("bases", []),
                "methods": cls.get("methods", []),
                "parent_classes": result.get("parent_classes", []),
                "child_classes": result.get("child_classes", []),
                "complexity_indicators": {
                    "has_docstring": bool(cls.get("docstring")),
                    "method_count": len(cls.get("methods", [])),
                    "inheritance_depth": len(result.get("parent_classes", [])),
                    "subclass_count": len(result.get("child_classes", [])),
                },
            }

            logger.info("Class analyzed", name=name)
            return ToolResult(
                success=True,
                data=analysis,
            )

        except Exception as e:
            logger.error("Failed to analyze class", name=name, error=str(e))
            return ToolResult(
                success=False,
                error=str(e),
            )

    def get_definition(self) -> ToolDefinition:
        """Get tool definition."""
        return ToolDefinition(
            name=self.name,
            description=self.description,
            parameters=[
                ToolParameter(
                    name="name",
                    description="Class name to analyze",
                    type="string",
                    required=True,
                ),
                ToolParameter(
                    name="module",
                    description="Optional module filter",
                    type="string",
                    required=False,
                ),
            ],
            category=self.category,
        )


class FindPatternsTool(MCPTool):
    """Tool to find design patterns in code."""

    name: str = "find_patterns"
    description: str = "Detect design patterns in the codebase"
    category: str = "analysis"

    async def execute(
        self, 
        pattern_type: Optional[str] = None,
        **kwargs
    ) -> ToolResult:
        """
        Find patterns.

        Args:
            pattern_type: Optional pattern type to search for

        Returns:
            ToolResult with found patterns
        """
        try:
            neo4j = get_neo4j_service()

            patterns = []

            # Find Singleton pattern - classes with no subclasses
            query = """
            MATCH (c:Class)
            WHERE NOT (c)<-[:INHERITS_FROM]-()
            AND NOT (c)-[:INHERITS_FROM]->()
            RETURN c.name AS name, c.module AS module
            LIMIT 20
            """
            singletons = await neo4j.execute_query(query)
            if singletons:
                patterns.append({
                    "type": "Potential_Singleton",
                    "description": "Classes with no inheritance",
                    "count": len(singletons),
                    "examples": singletons[:5],
                })

            # Find Decorator pattern - classes with decorators
            query = """
            MATCH (f:Function)
            WHERE size(f.decorators) > 0
            RETURN f.name AS name, f.module AS module, f.decorators AS decorators
            LIMIT 20
            """
            decorated = await neo4j.execute_query(query)
            if decorated:
                patterns.append({
                    "type": "Decorator_Pattern",
                    "description": "Decorated functions",
                    "count": len(decorated),
                    "examples": decorated[:5],
                })

            # Find Inheritance hierarchies
            query = """
            MATCH (c:Class)-[:INHERITS_FROM]->(parent)
            RETURN c.name AS child, parent.name AS parent
            LIMIT 20
            """
            inheritance = await neo4j.execute_query(query)
            if inheritance:
                patterns.append({
                    "type": "Inheritance_Hierarchy",
                    "description": "Class inheritance relationships",
                    "count": len(inheritance),
                    "examples": inheritance[:5],
                })

            logger.info("Patterns found", count=len(patterns))
            return ToolResult(
                success=True,
                data={
                    "patterns": patterns,
                    "total": len(patterns),
                },
            )

        except Exception as e:
            logger.error("Failed to find patterns", error=str(e))
            return ToolResult(
                success=False,
                error=str(e),
            )

    def get_definition(self) -> ToolDefinition:
        """Get tool definition."""
        return ToolDefinition(
            name=self.name,
            description=self.description,
            parameters=[
                ToolParameter(
                    name="pattern_type",
                    description="Optional pattern type to search for",
                    type="string",
                    required=False,
                ),
            ],
            category=self.category,
        )


class CompareImplementationsTool(MCPTool):
    """Tool to compare two implementations."""

    name: str = "compare_implementations"
    description: str = "Compare two code implementations"
    category: str = "analysis"

    async def execute(
        self,
        entity1: str,
        entity2: str,
    ) -> ToolResult:
        """
        Compare implementations.

        Args:
            entity1: First entity name
            entity2: Second entity name

        Returns:
            ToolResult with comparison
        """
        try:
            neo4j = get_neo4j_service()

            # Get both entities
            entity1_data = await neo4j.find_entity(entity1)
            entity2_data = await neo4j.find_entity(entity2)

            if not entity1_data or not entity2_data:
                return ToolResult(
                    success=False,
                    error="One or both entities not found",
                )

            comparison = {
                "entity1": {
                    "name": entity1_data.get("name"),
                    "type": "Class" if "bases" in entity1_data else "Function",
                    "docstring": entity1_data.get("docstring"),
                    "decorators": entity1_data.get("decorators", []),
                    "parameters": entity1_data.get("parameters", []),
                },
                "entity2": {
                    "name": entity2_data.get("name"),
                    "type": "Class" if "bases" in entity2_data else "Function",
                    "docstring": entity2_data.get("docstring"),
                    "decorators": entity2_data.get("decorators", []),
                    "parameters": entity2_data.get("parameters", []),
                },
                "similarities": {
                    "both_documented": bool(entity1_data.get("docstring")) and bool(entity2_data.get("docstring")),
                    "both_decorated": len(entity1_data.get("decorators", [])) > 0 and len(entity2_data.get("decorators", [])) > 0,
                },
                "differences": {
                    "parameter_count_diff": abs(
                        len(entity1_data.get("parameters", [])) -
                        len(entity2_data.get("parameters", []))
                    ),
                    "decorator_count_diff": abs(
                        len(entity1_data.get("decorators", [])) -
                        len(entity2_data.get("decorators", []))
                    ),
                },
            }

            logger.info("Implementations compared", entity1=entity1, entity2=entity2)
            return ToolResult(
                success=True,
                data=comparison,
            )

        except Exception as e:
            logger.error("Failed to compare implementations", error=str(e))
            return ToolResult(
                success=False,
                error=str(e),
            )

    def get_definition(self) -> ToolDefinition:
        """Get tool definition."""
        return ToolDefinition(
            name=self.name,
            description=self.description,
            parameters=[
                ToolParameter(
                    name="entity1",
                    description="First entity name",
                    type="string",
                    required=True,
                ),
                ToolParameter(
                    name="entity2",
                    description="Second entity name",
                    type="string",
                    required=True,
                ),
            ],
            category=self.category,
        )


class CodeAnalystAgent(BaseAgent):
    """
    Code Analyst Agent - Analyzes code and provides insights.

    Provides tools for:
    - Analyzing functions
    - Analyzing classes
    - Finding design patterns
    - Comparing implementations
    """

    name: str = "code_analyst"
    description: str = "Analyzes code patterns and provides insights"
    version = "1.0.0"

    def __init__(self):
        """Initialize code analyst agent."""
        super().__init__()

        # Register tools
        self.register_tool(AnalyzeFunctionTool())
        self.register_tool(AnalyzeClassTool())
        self.register_tool(FindPatternsTool())
        self.register_tool(CompareImplementationsTool())

        logger.info("CodeAnalystAgent initialized with 4 tools")

    async def initialize(self) -> None:
        """Initialize code analyst agent resources."""
        try:
            # Verify Neo4j connection
            neo4j = get_neo4j_service()
            logger.info("Code analyst agent ready")
        except Exception as e:
            logger.error("Failed to initialize code analyst agent", error=str(e))
            raise

    async def startup(self) -> None:
        """Start the code analyst agent."""
        await super().startup()
        await self.initialize()
        logger.info("Code analyst agent started")

    async def shutdown(self) -> None:
        """Shut down the code analyst agent."""
        await super().shutdown()
        logger.info("Code analyst agent shut down")
