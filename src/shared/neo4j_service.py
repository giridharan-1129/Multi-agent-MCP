"""
Neo4j Service for Knowledge Graph Operations.

WHAT: Manages all Neo4j database operations
WHY: Centralized interface for graph database access
HOW: Wraps Neo4j driver with type-safe, async operations

Example:
    service = Neo4jService()
    await service.connect()
    
    # Create nodes
    await service.create_class_node(name="FastAPI", file_path="main.py")
    
    # Query relationships
    result = await service.get_dependencies("FastAPI")
    
    await service.close()
"""

from typing import Any, Dict, List, Optional

from neo4j import AsyncDriver, AsyncSession, GraphDatabase
from neo4j.exceptions import Neo4jError as Neo4jDriverError

from .exceptions import Neo4jConnectionError, Neo4jError
from .logger import get_logger

logger = get_logger(__name__)


class Neo4jService:
    """
    Neo4j database service.

    Manages connections, schema, and queries to Neo4j knowledge graph.

    Attributes:
        driver: Neo4j driver instance
        uri: Database connection URI
        username: Database username
        password: Database password
        database: Database name
    """

    def __init__(
        self,
        uri: str = "bolt://localhost:7687",
        username: str = "neo4j",
        password: str = "password",
        database: str = "neo4j",
    ):
        """
        Initialize Neo4j service.

        Args:
            uri: Neo4j connection URI
            username: Database username
            password: Database password
            database: Database name
        """
        self.uri = uri
        self.username = username
        self.password = password
        self.database = database
        self.driver: Optional[AsyncDriver] = None

        logger.info(
            "Neo4jService initialized",
            uri=uri,
            database=database,
        )

    async def connect(self) -> None:
        """
        Connect to Neo4j database.

        Raises:
            Neo4jConnectionError: If connection fails
        """
        try:
            self.driver = GraphDatabase.driver(
                self.uri,
                auth=(self.username, self.password),
            )

            # Test connection
            async with self.driver.session(database=self.database) as session:
                await session.run("RETURN 1")

            logger.info("Connected to Neo4j", uri=self.uri)
        except Neo4jDriverError as e:
            logger.error("Failed to connect to Neo4j", error=str(e))
            raise Neo4jConnectionError(
                uri=self.uri,
                error_detail=str(e),
            )

    async def close(self) -> None:
        """Close Neo4j connection."""
        if self.driver:
            await self.driver.close()
            logger.info("Closed Neo4j connection")

    async def create_schema(self) -> None:
        """
        Create knowledge graph schema.

        Creates indexes and constraints for optimal performance.
        """
        if not self.driver:
            raise Neo4jConnectionError(
                uri=self.uri,
                error_detail="Driver not connected",
            )

        try:
            async with self.driver.session(database=self.database) as session:
                # Create constraints for unique properties
                queries = [
                    # Module nodes
                    "CREATE CONSTRAINT module_path IF NOT EXISTS FOR (m:Module) REQUIRE m.file_path IS UNIQUE",
                    
                    # Class nodes
                    "CREATE CONSTRAINT class_unique IF NOT EXISTS FOR (c:Class) REQUIRE (c.name, c.module) IS UNIQUE",
                    
                    # Function nodes
                    "CREATE CONSTRAINT function_unique IF NOT EXISTS FOR (f:Function) REQUIRE (f.name, f.module) IS UNIQUE",
                    
                    # Create indexes for faster queries
                    "CREATE INDEX class_name IF NOT EXISTS FOR (c:Class) ON (c.name)",
                    "CREATE INDEX function_name IF NOT EXISTS FOR (f:Function) ON (f.name)",
                    "CREATE INDEX module_name IF NOT EXISTS FOR (m:Module) ON (m.name)",
                ]

                for query in queries:
                    try:
                        await session.run(query)
                    except Neo4jDriverError as e:
                        # Constraint might already exist, that's ok
                        if "already exists" not in str(e):
                            logger.warning(f"Schema creation warning: {e}")

            logger.info("Knowledge graph schema created/verified")
        except Neo4jDriverError as e:
            logger.error("Failed to create schema", error=str(e))
            raise Neo4jError(
                query="CREATE SCHEMA",
                error_detail=str(e),
            )

    async def execute_query(self, query: str, params: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
        """
        Execute a Cypher query.

        Args:
            query: Cypher query string
            params: Query parameters

        Returns:
            List of result records

        Raises:
            Neo4jError: If query execution fails
        """
        if not self.driver:
            raise Neo4jConnectionError(
                uri=self.uri,
                error_detail="Driver not connected",
            )

        try:
            async with self.driver.session(database=self.database) as session:
                result = await session.run(query, params or {})
                records = await result.data()
                return records
        except Neo4jDriverError as e:
            logger.error("Query execution failed", query=query, error=str(e))
            raise Neo4jError(query=query, error_detail=str(e))

    async def create_module_node(
        self,
        name: str,
        file_path: str,
        content: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Create a Module node in the graph.

        Args:
            name: Module name
            file_path: Path to file
            content: File content (optional)

        Returns:
            Created node data

        Raises:
            Neo4jError: If creation fails
        """
        query = """
        CREATE (m:Module {
            name: $name,
            file_path: $file_path,
            content: $content,
            created_at: timestamp()
        })
        RETURN m { .* } AS module
        """

        try:
            result = await self.execute_query(
                query,
                {
                    "name": name,
                    "file_path": file_path,
                    "content": content,
                },
            )
            logger.info("Module node created", name=name, file_path=file_path)
            return result[0]["module"] if result else {}
        except Neo4jError as e:
            logger.error("Failed to create module node", name=name, error=str(e))
            raise

    async def create_class_node(
        self,
        name: str,
        module: str,
        docstring: Optional[str] = None,
        line_number: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Create a Class node in the graph.

        Args:
            name: Class name
            module: Module where class is defined
            docstring: Class docstring
            line_number: Line number in file

        Returns:
            Created node data

        Raises:
            Neo4jError: If creation fails
        """
        query = """
        CREATE (c:Class {
            name: $name,
            module: $module,
            docstring: $docstring,
            line_number: $line_number,
            created_at: timestamp()
        })
        RETURN c { .* } AS class
        """

        try:
            result = await self.execute_query(
                query,
                {
                    "name": name,
                    "module": module,
                    "docstring": docstring,
                    "line_number": line_number,
                },
            )
            logger.info("Class node created", name=name, module=module)
            return result[0]["class"] if result else {}
        except Neo4jError as e:
            logger.error("Failed to create class node", name=name, error=str(e))
            raise

    async def create_function_node(
        self,
        name: str,
        module: str,
        docstring: Optional[str] = None,
        line_number: Optional[int] = None,
        is_async: bool = False,
    ) -> Dict[str, Any]:
        """
        Create a Function node in the graph.

        Args:
            name: Function name
            module: Module where function is defined
            docstring: Function docstring
            line_number: Line number in file
            is_async: Whether function is async

        Returns:
            Created node data

        Raises:
            Neo4jError: If creation fails
        """
        query = """
        CREATE (f:Function {
            name: $name,
            module: $module,
            docstring: $docstring,
            line_number: $line_number,
            is_async: $is_async,
            created_at: timestamp()
        })
        RETURN f { .* } AS function
        """

        try:
            result = await self.execute_query(
                query,
                {
                    "name": name,
                    "module": module,
                    "docstring": docstring,
                    "line_number": line_number,
                    "is_async": is_async,
                },
            )
            logger.info("Function node created", name=name, module=module)
            return result[0]["function"] if result else {}
        except Neo4jError as e:
            logger.error("Failed to create function node", name=name, error=str(e))
            raise

    async def create_relationship(
        self,
        source_name: str,
        target_name: str,
        rel_type: str,
        properties: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """
        Create a relationship between nodes.

        Args:
            source_name: Source node name/identifier
            target_name: Target node name/identifier
            rel_type: Relationship type (e.g., IMPORTS, INHERITS_FROM, CALLS)
            properties: Relationship properties

        Returns:
            True if successful

        Raises:
            Neo4jError: If creation fails
        """
        query = f"""
        MATCH (source), (target)
        WHERE source.name = $source_name OR source.file_path = $source_name
        AND (target.name = $target_name OR target.file_path = $target_name)
        CREATE (source)-[r:{rel_type} $props]->(target)
        RETURN count(r) AS count
        """

        try:
            result = await self.execute_query(
                query,
                {
                    "source_name": source_name,
                    "target_name": target_name,
                    "props": properties or {},
                },
            )
            logger.info(
                "Relationship created",
                source=source_name,
                target=target_name,
                type=rel_type,
            )
            return True
        except Neo4jError as e:
            logger.error("Failed to create relationship", error=str(e))
            raise

    async def find_entity(self, name: str, entity_type: Optional[str] = None) -> Dict[str, Any]:
        """
        Find an entity by name.

        Args:
            name: Entity name to search
            entity_type: Optional type filter (Class, Function, Module)

        Returns:
            Entity data if found

        Raises:
            Neo4jError: If query fails
        """
        if entity_type:
            query = f"""
            MATCH (e:{entity_type})
            WHERE e.name = $name
            RETURN e {{ .* }} AS entity
            LIMIT 1
            """
        else:
            query = """
            MATCH (e)
            WHERE e.name = $name
            RETURN e { .* } AS entity
            LIMIT 1
            """

        try:
            result = await self.execute_query(query, {"name": name})
            if result:
                logger.info("Entity found", name=name, type=entity_type)
                return result[0]["entity"]
            logger.info("Entity not found", name=name, type=entity_type)
            return {}
        except Neo4jError as e:
            logger.error("Failed to find entity", name=name, error=str(e))
            raise

    async def get_dependencies(self, entity_name: str) -> List[Dict[str, Any]]:
        """
        Get all dependencies of an entity.

        Args:
            entity_name: Entity to find dependencies for

        Returns:
            List of dependent entities

        Raises:
            Neo4jError: If query fails
        """
        query = """
        MATCH (entity)-[r:IMPORTS|INHERITS_FROM|CALLS]->(dep)
        WHERE entity.name = $name
        RETURN dep { .* } AS dependency, type(r) AS relationship_type
        """

        try:
            result = await self.execute_query(query, {"name": entity_name})
            logger.info("Dependencies retrieved", entity=entity_name, count=len(result))
            return result
        except Neo4jError as e:
            logger.error("Failed to get dependencies", entity=entity_name, error=str(e))
            raise

    async def get_dependents(self, entity_name: str) -> List[Dict[str, Any]]:
        """
        Get all entities that depend on a given entity.

        Args:
            entity_name: Entity to find dependents for

        Returns:
            List of dependent entities

        Raises:
            Neo4jError: If query fails
        """
        query = """
        MATCH (dep)-[r:IMPORTS|INHERITS_FROM|CALLS]->(entity)
        WHERE entity.name = $name
        RETURN dep { .* } AS dependent, type(r) AS relationship_type
        """

        try:
            result = await self.execute_query(query, {"name": entity_name})
            logger.info("Dependents retrieved", entity=entity_name, count=len(result))
            return result
        except Neo4jError as e:
            logger.error("Failed to get dependents", entity=entity_name, error=str(e))
            raise

    async def clear_database(self) -> bool:
        """
        Clear all nodes and relationships from database.

        WARNING: This deletes all data!

        Returns:
            True if successful
        """
        query = "MATCH (n) DETACH DELETE n"

        try:
            await self.execute_query(query)
            logger.warning("Database cleared - all nodes and relationships deleted")
            return True
        except Neo4jError as e:
            logger.error("Failed to clear database", error=str(e))
            raise

    async def get_graph_statistics(self) -> Dict[str, int]:
        """
        Get statistics about the knowledge graph.

        Returns:
            Dictionary with node and relationship counts
        """
        try:
            nodes_result = await self.execute_query(
                "MATCH (n) RETURN labels(n) AS labels, count(*) AS count"
            )
            rels_result = await self.execute_query(
                "MATCH ()-[r]->() RETURN type(r) AS type, count(*) AS count"
            )

            stats = {
                "total_nodes": sum(r["count"] for r in nodes_result),
                "total_relationships": sum(r["count"] for r in rels_result),
                "node_types": {r["labels"][0]: r["count"] for r in nodes_result if r["labels"]},
                "relationship_types": {r["type"]: r["count"] for r in rels_result},
            }

            logger.info("Graph statistics retrieved", stats=stats)
            return stats
        except Neo4jError as e:
            logger.error("Failed to get graph statistics", error=str(e))
            raise


# Global Neo4j service instance
neo4j_service: Optional[Neo4jService] = None


async def init_neo4j_service(
    uri: str = "bolt://localhost:7687",
    username: str = "neo4j",
    password: str = "password",
    database: str = "neo4j",
) -> Neo4jService:
    """
    Initialize and connect Neo4j service.

    Args:
        uri: Neo4j connection URI
        username: Database username
        password: Database password
        database: Database name

    Returns:
        Connected Neo4jService instance
    """
    global neo4j_service
    neo4j_service = Neo4jService(uri, username, password, database)
    await neo4j_service.connect()
    await neo4j_service.create_schema()
    return neo4j_service


async def get_neo4j_service() -> Neo4jService:
    """
    Get initialized Neo4j service.

    Returns:
        Neo4jService instance

    Raises:
        RuntimeError: If service not initialized
    """
    global neo4j_service
    if not neo4j_service:
        raise RuntimeError("Neo4j service not initialized. Call init_neo4j_service() first.")
    return neo4j_service
