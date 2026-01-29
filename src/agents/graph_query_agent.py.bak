"""
Graph Query Agent - MCP Agent for Knowledge Graph Queries.

WHAT: MCP agent that queries the Neo4j knowledge graph
WHY: Find entities, relationships, dependencies, and analyze code structure
HOW: Execute Cypher queries against Neo4j, return structured results

Example:
    agent = GraphQueryAgent()
    await agent.startup()
    
    result = await agent.execute_tool("find_entity", {
        "name": "FastAPI",
        "entity_type": "Class"
    })
"""

from typing import Any, Dict, List, Optional

from ..shared.base_agent import BaseAgent
from ..shared.exceptions import Neo4jError, EntityNotFoundError
from ..shared.logger import get_logger
from ..shared.mcp_types import MCPTool, ToolResult, ToolParameter, ToolDefinition
from ..shared.neo4j_service import get_neo4j_service

logger = get_logger(__name__)


class FindEntityTool(MCPTool):
    """Tool to find entities in the knowledge graph."""

    name = "find_entity"
    description = "Find a class, function, or module by name"
    category = "query"

    async def execute(
        self,
        name: str,
        entity_type: Optional[str] = None,
    ) -> ToolResult:
        """
        Find an entity.

        Args:
            name: Entity name to search for
            entity_type: Optional filter (Class, Function, Module)

        Returns:
            ToolResult with entity data
        """
        try:
            neo4j = get_neo4j_service()
            entity = await neo4j.find_entity(name, entity_type)

            if not entity:
                logger.info("Entity not found", name=name, type=entity_type)
                return ToolResult(
                    success=False,
                    error=f"Entity '{name}' not found",
                )

            logger.info("Entity found", name=name, type=entity_type)
            return ToolResult(
                success=True,
                data={"entity": entity},
            )

        except Exception as e:
            logger.error("Failed to find entity", name=name, error=str(e))
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
                    description="Name of entity to find",
                    type="string",
                    required=True,
                ),
                ToolParameter(
                    name="entity_type",
                    description="Type of entity (Class, Function, Module)",
                    type="string",
                    required=False,
                ),
            ],
            category=self.category,
        )


class GetDependenciesTool(MCPTool):
    """Tool to get dependencies of an entity."""

    name = "get_dependencies"
    description = "Find all entities that a given entity depends on"
    category = "query"

    async def execute(self, name: str) -> ToolResult:
        """
        Get dependencies.

        Args:
            name: Entity name

        Returns:
            ToolResult with dependencies
        """
        try:
            neo4j = get_neo4j_service()
            dependencies = await neo4j.get_dependencies(name)

            logger.info("Dependencies retrieved", entity=name, count=len(dependencies))
            return ToolResult(
                success=True,
                data={
                    "entity": name,
                    "dependencies": dependencies,
                    "count": len(dependencies),
                },
            )

        except Exception as e:
            logger.error("Failed to get dependencies", entity=name, error=str(e))
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
                    description="Entity name to find dependencies for",
                    type="string",
                    required=True,
                ),
            ],
            category=self.category,
        )


class GetDependentsTool(MCPTool):
    """Tool to get entities that depend on a given entity."""

    name = "get_dependents"
    description = "Find all entities that depend on a given entity"
    category = "query"

    async def execute(self, name: str) -> ToolResult:
        """
        Get dependents.

        Args:
            name: Entity name

        Returns:
            ToolResult with dependents
        """
        try:
            neo4j = get_neo4j_service()
            dependents = await neo4j.get_dependents(name)

            logger.info("Dependents retrieved", entity=name, count=len(dependents))
            return ToolResult(
                success=True,
                data={
                    "entity": name,
                    "dependents": dependents,
                    "count": len(dependents),
                },
            )

        except Exception as e:
            logger.error("Failed to get dependents", entity=name, error=str(e))
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
                    description="Entity name to find dependents for",
                    type="string",
                    required=True,
                ),
            ],
            category=self.category,
        )


class ExecuteQueryTool(MCPTool):
    """Tool to execute custom Cypher queries."""

    name = "execute_query"
    description = "Execute a custom Cypher query against the knowledge graph"
    category = "query"

    async def execute(
        self,
        query: str,
        params: Optional[Dict[str, Any]] = None,
    ) -> ToolResult:
        """
        Execute a Cypher query.

        Args:
            query: Cypher query string
            params: Optional query parameters

        Returns:
            ToolResult with query results
        """
        try:
            neo4j = get_neo4j_service()
            results = await neo4j.execute_query(query, params)

            logger.info("Query executed", query_length=len(query), results=len(results))
            return ToolResult(
                success=True,
                data={
                    "query": query,
                    "results": results,
                    "count": len(results),
                },
            )

        except Exception as e:
            logger.error("Query execution failed", query=query, error=str(e))
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
                    name="query",
                    description="Cypher query to execute",
                    type="string",
                    required=True,
                ),
                ToolParameter(
                    name="params",
                    description="Query parameters (optional)",
                    type="object",
                    required=False,
                ),
            ],
            category=self.category,
        )


class SearchEntitiesTool(MCPTool):
    """Tool to search for entities by pattern."""

    name = "search_entities"
    description = "Search for entities matching a pattern"
    category = "query"

    async def execute(
        self,
        pattern: str,
        entity_type: Optional[str] = None,
    ) -> ToolResult:
        """
        Search for entities.

        Args:
            pattern: Search pattern (supports * wildcard)
            entity_type: Optional type filter (Class, Function, Module)

        Returns:
            ToolResult with matching entities
        """
        try:
            neo4j = get_neo4j_service()

            # Build Cypher query with pattern matching
            if entity_type:
                query = f"""
                MATCH (e:{entity_type})
                WHERE e.name CONTAINS $pattern
                RETURN e {{ .* }} AS entity
                LIMIT 50
                """
            else:
                query = """
                MATCH (e)
                WHERE e.name CONTAINS $pattern
                RETURN e { .* } AS entity
                LIMIT 50
                """

            results = await neo4j.execute_query(query, {"pattern": pattern})

            logger.info("Entities searched", pattern=pattern, results=len(results))
            return ToolResult(
                success=True,
                data={
                    "pattern": pattern,
                    "results": [r["entity"] for r in results],
                    "count": len(results),
                },
            )

        except Exception as e:
            logger.error("Search failed", pattern=pattern, error=str(e))
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
                    name="pattern",
                    description="Search pattern (supports * wildcard)",
                    type="string",
                    required=True,
                ),
                ToolParameter(
                    name="entity_type",
                    description="Optional type filter (Class, Function, Module)",
                    type="string",
                    required=False,
                ),
            ],
            category=self.category,
        )


class GetRelationshipsTool(MCPTool):
    """Tool to get relationships between entities."""

    name = "get_relationships"
    description = "Find relationships between two entities"
    category = "query"

    async def execute(
        self,
        source: str,
        target: str,
        rel_type: Optional[str] = None,
    ) -> ToolResult:
        """
        Get relationships.

        Args:
            source: Source entity name
            target: Target entity name
            rel_type: Optional relationship type filter

        Returns:
            ToolResult with relationships
        """
        try:
            neo4j = get_neo4j_service()

            if rel_type:
                query = f"""
                MATCH (s)-[r:{rel_type}]->(t)
                WHERE s.name = $source AND t.name = $target
                RETURN s {{ .* }} AS source, t {{ .* }} AS target, 
                       type(r) AS relationship_type, r {{ .* }} AS relationship_data
                """
            else:
                query = """
                MATCH (s)-[r]->(t)
                WHERE s.name = $source AND t.name = $target
                RETURN s { .* } AS source, t { .* } AS target, 
                       type(r) AS relationship_type, r { .* } AS relationship_data
                """

            results = await neo4j.execute_query(
                query,
                {"source": source, "target": target},
            )

            logger.info(
                "Relationships retrieved",
                source=source,
                target=target,
                count=len(results),
            )
            return ToolResult(
                success=True,
                data={
                    "source": source,
                    "target": target,
                    "relationships": results,
                    "count": len(results),
                },
            )

        except Exception as e:
            logger.error(
                "Failed to get relationships",
                source=source,
                target=target,
                error=str(e),
            )
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
                    name="source",
                    description="Source entity name",
                    type="string",
                    required=True,
                ),
                ToolParameter(
                    name="target",
                    description="Target entity name",
                    type="string",
                    required=True,
                ),
                ToolParameter(
                    name="rel_type",
                    description="Relationship type filter (optional)",
                    type="string",
                    required=False,
                ),
            ],
            category=self.category,
        )


class GraphQueryAgent(BaseAgent):
    """
    Graph Query Agent - Queries the knowledge graph.

    Provides tools for:
    - Finding entities
    - Getting dependencies
    - Getting dependents
    - Executing custom queries
    - Searching entities
    - Getting relationships
    """

    name = "graph_query"
    description = "Queries the knowledge graph for entities and relationships"
    version = "1.0.0"

    def __init__(self):
        """Initialize graph query agent."""
        super().__init__()

        # Register tools
        self.register_tool(FindEntityTool())
        self.register_tool(GetDependenciesTool())
        self.register_tool(GetDependentsTool())
        self.register_tool(ExecuteQueryTool())
        self.register_tool(SearchEntitiesTool())
        self.register_tool(GetRelationshipsTool())

        logger.info("GraphQueryAgent initialized with 6 tools")

    async def initialize(self) -> None:
        """Initialize graph query agent resources."""
        try:
            # Verify Neo4j connection
            neo4j = get_neo4j_service()
            logger.info("Graph query agent ready")
        except Exception as e:
            logger.error("Failed to initialize graph query agent", error=str(e))
            raise

    async def startup(self) -> None:
        """Start the graph query agent."""
        await super().startup()
        await self.initialize()
        logger.info("Graph query agent started")

    async def shutdown(self) -> None:
        """Shut down the graph query agent."""
        await super().shutdown()
        logger.info("Graph query agent shut down")
