"""
Neo4j Database Service.

Handles all Neo4j database operations for the knowledge graph.
"""

from typing import Any, Dict, List, Optional
from fastapi.concurrency import run_in_threadpool

import logging

logger = logging.getLogger(__name__)


class Neo4jService:
    """Service for Neo4j database operations."""

    def __init__(
        self,
        uri: str = "bolt://localhost:7687",
        username: str = "neo4j",
        password: str = "password",
        database: str = "neo4j",
    ):
        """Initialize Neo4j service."""
        self.uri = uri
        self.username = username
        self.password = password
        self.database = database
        self.driver = None
        
    async def connect(self) -> bool:
        from neo4j import GraphDatabase
        import asyncio

        retries = 10
        delay = 2

        for attempt in range(1, retries + 1):
            try:
                self.driver = GraphDatabase.driver(
                    self.uri,
                    auth=(self.username, self.password)
                )

                with self.driver.session(database=self.database) as session:
                    session.run("RETURN 1")

                logger.info(f"Connected to Neo4j: {self.uri}")
                return True

            except Exception as e:
                logger.warning(f"Failed to connect to Neo4j: {e}")
                await asyncio.sleep(delay)

        logger.error("Neo4j connection failed after retries")
        return False

    async def close(self) -> None:
        """Close Neo4j connection."""
        if self.driver:
            self.driver.close()
            logger.info("Neo4j connection closed")

    async def clear_database(self) -> None:
        def _run():
            with self.driver.session(database=self.database) as session:
                session.run("MATCH (n) DETACH DELETE n")

        await run_in_threadpool(_run)
    async def create_class_node(
        self,
        name: str,
        module: str,
        docstring: str = None,
        line_number: int = None,
    ):
        def _run():
            with self.driver.session(database=self.database) as session:
                session.run(
                    """
                    MERGE (c:Class {name: $name, module: $module})
                    SET c.docstring = $docstring,
                        c.line_number = $line_number
                    """,
                    {
                        "name": name,
                        "module": module,
                        "docstring": docstring,
                        "line_number": line_number,
                    },
                )

        await run_in_threadpool(_run)
    async def create_function_node(
        self,
        name: str,
        module: str,
        docstring: str = None,
        line_number: int = None,
        is_async: bool = False,
    ):
        def _run():
            with self.driver.session(database=self.database) as session:
                session.run(
                    """
                    MERGE (f:Function {name: $name, module: $module})
                    SET f.docstring = $docstring,
                        f.line_number = $line_number,
                        f.is_async = $is_async
                    """,
                    {
                        "name": name,
                        "module": module,
                        "docstring": docstring,
                        "line_number": line_number,
                        "is_async": is_async,
                    },
                )

        await run_in_threadpool(_run)

    async def create_file_node(self, path: str):
        def _run():
            with self.driver.session(database=self.database) as session:
                # Extract filename from path
                filename = path.split("/")[-1]
                session.run(
                    """
                    MERGE (f:File {path: $path})
                    SET f.name = $name
                    """,
                    {"path": path, "name": filename},
                )

        await run_in_threadpool(_run)

    async def create_method_node(self, name, module, docstring, line_number, is_async):
        def _run():
            with self.driver.session(database=self.database) as session:
                session.run(
                            """
                            MERGE (m:Method {name: $name, module: $module})
                            SET m.docstring = $docstring,
                                m.line_number = $line_number,
                                m.is_async = $is_async
                            """,
                            {
                                "name": name,
                                "module": module,
                                "docstring": docstring,
                                "line_number": line_number,
                                "is_async": is_async,
                            }
                        )

        await run_in_threadpool(_run)

    async def create_parameter_node(self, name, param_name, module):
        def _run():
            with self.driver.session(database=self.database) as session:
                session.run("""
                MERGE (p:Parameter {name: $name})
                SET p.param_name = $param_name,
                    p.module = $module
                """, {"name": name, "param_name": param_name, "module": module})
        await run_in_threadpool(_run)

    async def create_type_node(self, name):
        def _run():
            with self.driver.session(database=self.database) as session:
                session.run("""
                MERGE (t:Type {name: $name})
                """, {"name": name})
        await run_in_threadpool(_run)


    async def create_docstring_node(
        self,
        name: str,
        content: str,
        scope: str,
        module: str,
        package: Optional[str] = None,
    ) -> None:
        """
        Create a Docstring node.

        Args:
            name: Unique docstring identifier
            content: Docstring text
            scope: Class | Function | Module
            module: File path
            package: Package name
        """
        def _run():
            with self.driver.session(database=self.database) as session:
                session.run(
                    """
                    MERGE (d:Docstring {name: $name})
                    SET d.content = $content,
                        d.scope = $scope,
                        d.module = $module,
                        d.package = $package
                    """,
                    {
                        "name": name,
                        "content": content,
                        "scope": scope,
                        "module": module,
                        "package": package,
                    },
                )

        await run_in_threadpool(_run)

    async def create_relationship(
        self,
        source_name: str,
        source_label: str,
        target_name: str,
        target_label: str,
        rel_type: str,
        properties: Dict = None,
    ):
        def _run():
            try:
                with self.driver.session(database=self.database) as session:
                    # Build match clauses - File nodes match on 'path', others on 'name'
                    source_prop = 'path' if source_label == 'File' else 'name'
                    target_prop = 'path' if target_label == 'File' else 'name'

                    # ✅ For external classes (e.g., Exception from builtins), MERGE them first
                    if target_label in ['Class', 'Function'] and not session.run(
                        f"MATCH (b:{target_label} {{{target_prop}: $target}}) RETURN b LIMIT 1",
                        {"target": target_name}
                    ).single():
                        # External entity doesn't exist, create it as a stub
                        session.run(
                            f"""
                            MERGE (b:{target_label} {{{target_prop}: $target}})
                            SET b.external = true
                            """,
                            {"target": target_name}
                        )

                    session.run(
                        f"""
                        MATCH (a:{source_label} {{{source_prop}: $source}})
                        MATCH (b:{target_label} {{{target_prop}: $target}})
                        MERGE (a)-[r:{rel_type}]->(b)
                        SET r += $props
                        """,
                        {
                            "source": source_name,
                            "target": target_name,
                            "props": properties or {},
                        },
                    )
            except Exception as e:
                logger.debug(f"Failed to create {rel_type} relationship: {str(e)}")

        await run_in_threadpool(_run)



    async def create_defines_relationship(
        self,
        file_path: str,
        target_name: str,
        target_module: str,
        target_type: str,
    ):
        def _run():
            try:
                with self.driver.session(database=self.database) as session:
                    session.run(
                        f"""
                        MATCH (f:File {{path: $file}})
                        MATCH (t:{target_type} {{name: $name, module: $module}})
                        MERGE (f)-[:DEFINES]->(t)
                        """,
                        {
                            "file": file_path,
                            "name": target_name,
                            "module": target_module,
                        },
                    )
            except Exception as e:
                logger.debug(f"Failed to create DEFINES relationship for {target_name}: {str(e)}")

        await run_in_threadpool(_run)



    async def execute_query(self, query: str, params: Optional[Dict] = None) -> List[Dict]:
        if not self.driver:
            return []

        def _run():
            with self.driver.session(database=self.database) as session:
                result = session.run(query, params or {})
                return [record.data() for record in result]

        try:
            return await run_in_threadpool(_run)
        except Exception as e:
            logger.error(f"Query execution failed: {str(e)}")
            return []

    async def find_entity(self, name: str, entity_type: Optional[str] = None):
        try:
            if not self.driver:
                return {}

            label = entity_type if entity_type else ""

            def _run():
                with self.driver.session(database=self.database) as session:
                    # 1Ã¯Â¸ÂÃ¢Æ’Â£ Exact match (case-insensitive)
                    query_exact = f"""
                    MATCH (n{':' + label if label else ''})
                    WHERE toLower(n.name) = toLower($name)
                    RETURN n
                    LIMIT 1
                    """

                    result = session.run(query_exact, {"name": name})
                    record = result.single()
                    if record:
                        return record["n"]

                    # 2Ã¯Â¸ÂÃ¢Æ’Â£ Fallback: contains
                    query_contains = f"""
                    MATCH (n{':' + label if label else ''})
                    WHERE toLower(n.name) CONTAINS toLower($name)
                    RETURN n
                    LIMIT 1
                    """

                    result = session.run(query_contains, {"name": name})
                    record = result.single()
                    if record:
                        return record["n"]

                    return None

            node = await run_in_threadpool(_run)
            return {"entity": dict(node) if node else None}

        except Exception as e:
            logger.error(f"Failed to find entity: {str(e)}")
            return {}
    async def create_package_node(self, name: str):
        def _run():
            with self.driver.session(database=self.database) as session:
                session.run(
                    """
                    MERGE (p:Package {name: $name})
                    """,
                    {"name": name},
                )

        await run_in_threadpool(_run)
    async def search_entities(self, query_text: str, limit: int = 5) -> List[Dict]:
            """Search for entities matching query text."""
            def _run():
                with self.driver.session(database=self.database) as session:
                    cypher = """
                    MATCH (n)
                    WHERE n.name IS NOT NULL 
                    AND (toLower(n.name) CONTAINS toLower($query) 
                        OR toLower(n.docstring) CONTAINS toLower($query))
                    RETURN {
                        name: n.name,
                        type: labels(n)[0],
                        module: n.module,
                        docstring: n.docstring,
                        line_number: n.line_number
                    } as entity
                    LIMIT $limit
                    """
                    result = session.run(cypher, {"query": query_text, "limit": limit})
                    return [record["entity"] for record in result]
            
            try:
                return await run_in_threadpool(_run)
            except Exception as e:
                logger.error(f"Entity search failed: {str(e)}")
                return []

    async def get_entity_context(self, entity_name: str) -> Dict:
            """Get full context for an entity including relationships."""
            def _run():
                with self.driver.session(database=self.database) as session:
                    cypher = """
                    MATCH (n {name: $name})
                    OPTIONAL MATCH (n)-[r]->(related)
                    RETURN {
                        entity: {
                            name: n.name,
                            type: labels(n)[0],
                            module: n.module,
                            docstring: n.docstring,
                            line_number: n.line_number
                        },
                        relationships: collect({
                            type: type(r),
                            target: related.name
                        })
                    } as context
                    """
                    result = session.run(cypher, {"name": entity_name})
                    record = result.single()
                    return record["context"] if record else None
            
            try:
                return await run_in_threadpool(_run)
            except Exception as e:
                logger.error(f"Failed to get entity context: {str(e)}")
                return None

    async def get_dependencies(self, entity_name: str) -> List[Dict]:
        """Get all entities that a given entity depends on."""
        def _run():
            with self.driver.session(database=self.database) as session:
                cypher = """
                MATCH (source)
                WHERE source.name = $name
                MATCH (source)-[r]->(target)
                WHERE type(r) IN ['IMPORTS', 'CALLS', 'INHERITS_FROM', 'CONTAINS']
                RETURN {
                    target_name: target.name,
                    target_type: labels(target)[0],
                    relationship_type: type(r),
                    target_module: target.module
                } as dependency
                """
                result = session.run(cypher, {"name": entity_name})
                return [record["dependency"] for record in result]
        
        try:
            return await run_in_threadpool(_run)
        except Exception as e:
            logger.error(f"Failed to get dependencies: {str(e)}")
            return []

    async def get_dependents(self, entity_name: str) -> List[Dict]:
        """Get all entities that depend on a given entity."""
        def _run():
            with self.driver.session(database=self.database) as session:
                cypher = """
                MATCH (target)
                WHERE target.name = $name
                MATCH (source)-[r]->(target)
                WHERE type(r) IN ['IMPORTS', 'CALLS', 'INHERITS_FROM', 'CONTAINS']
                RETURN {
                    source_name: source.name,
                    source_type: labels(source)[0],
                    relationship_type: type(r),
                    source_module: source.module
                } as dependent
                """
                result = session.run(cypher, {"name": entity_name})
                return [record["dependent"] for record in result]
        
        try:
            return await run_in_threadpool(_run)
        except Exception as e:
            logger.error(f"Failed to get dependents: {str(e)}")
            return []

    async def get_relationships(self, entity_name: str, relationship_type: str = None) -> List[Dict]:
        def _run():
            with self.driver.session(database=self.database) as session:
                # === BELONGS_TO (upward ownership) ===
                if relationship_type == "BELONGS_TO":
                    cypher = """
                    MATCH (e)
                    WHERE e.name = $name
                    MATCH (e)<-[:DEFINES]-(f:File)<-[:CONTAINS]-(p:Package)
                    RETURN {
                        target_name: p.name,
                        target_type: "Package",
                        relationship_type: "BELONGS_TO",
                        target_module: null
                    } AS relationship
                    """
                    result = session.run(cypher, {"name": entity_name})
                    return [r["relationship"] for r in result]


                # === CONTAINS (polymorphic, correct) ===
                # Smart CONTAINS
                if relationship_type == "CONTAINS":
                    cypher = """
                    MATCH (p:Package)
                    WHERE p.name = $name
                    MATCH (p)-[:CONTAINS]->(f:File)
                    RETURN {
                        target_name: f.path,
                        target_type: "File",
                        relationship_type: "CONTAINS",
                        target_module: f.path
                    } AS relationship
                    """
                    result = session.run(cypher, {"name": entity_name})
                    return [r["relationship"] for r in result]

                # === DEFINES (File → Class/Function ONLY) ===
                if relationship_type == "DEFINES":
                    cypher = """
                    MATCH (f:File)
                    WHERE f.path = $name
                    MATCH (f)-[:DEFINES]->(e)
                    RETURN {
                        target_name: e.name,
                        target_type: labels(e)[0],
                        relationship_type: "DEFINES",
                        target_module: e.module
                    } AS relationship
                    """
                    result = session.run(cypher, {"name": entity_name})
                    return [r["relationship"] for r in result]

                # === Other relationships (bidirectional) ===
                if relationship_type:
                    cypher = """
                    MATCH (e)
                    WHERE e.name = $name
                    MATCH (e)-[r]-(other)
                    WHERE type(r) = $rel
                    RETURN {
                        target_name: coalesce(other.name, other.path),
                        target_type: labels(other)[0],
                        relationship_type: type(r),
                        target_module: other.module
                    } AS relationship
                    """
                    result = session.run(
                        cypher,
                        {"name": entity_name, "rel": relationship_type},
                    )
                else:
                    cypher = """
                    MATCH (e)
                    WHERE e.name = $name
                    MATCH (e)-[r]-(other)
                    RETURN {
                        target_name: coalesce(other.name, other.path),
                        target_type: labels(other)[0],
                        relationship_type: type(r),
                        target_module: other.module
                    } AS relationship
                    """
                    result = session.run(cypher, {"name": entity_name})

                return [r["relationship"] for r in result]

        return await run_in_threadpool(_run)
    async def create_external_class_node(
        self,
        name: str,
        module: str = "builtins",
    ):
        """Create a stub node for external classes (e.g., Exception from builtins)."""
        def _run():
            with self.driver.session(database=self.database) as session:
                session.run(
                    """
                    MERGE (c:Class {name: $name, module: $module})
                    SET c.external = true,
                        c.docstring = "External class"
                    """,
                    {
                        "name": name,
                        "module": module,
                    },
                )

        await run_in_threadpool(_run)
    async def get_graph_statistics(self) -> Dict[str, Any]:
            """Get graph statistics."""
            try:
                if not self.driver:
                    return {"nodes": {}, "relationships": {}}
                
                with self.driver.session(database=self.database) as session:
                    # Count nodes by label
                    node_query = "MATCH (n) RETURN labels(n)[0] as label, count(*) as count"
                    node_result = session.run(node_query)
                    nodes = {record["label"]: record["count"] for record in node_result}
                    
                    # Count relationships
                    rel_query = "MATCH ()-[r]->() RETURN type(r) as type, count(*) as count"
                    rel_result = session.run(rel_query)
                    relationships = {record["type"]: record["count"] for record in rel_result}
                    
                    return {
                        "nodes": nodes,
                        "relationships": relationships,
                    }
                    
            except Exception as e:
                logger.error(f"Failed to get statistics: {str(e)}")
                return {"nodes": {}, "relationships": {}}


    # Global instance
_neo4j_service: Optional[Neo4jService] = None


async def init_neo4j_service(
        uri: str = "bolt://localhost:7687",
        username: str = "neo4j",
        password: str = "password",
        database: str = "neo4j",
    ) -> Neo4jService:
        """Initialize the global Neo4j service."""
        global _neo4j_service
        
        _neo4j_service = Neo4jService(uri, username, password, database)
        await _neo4j_service.connect()
        return _neo4j_service

def get_neo4j_service() -> Neo4jService:
    global _neo4j_service
    if _neo4j_service is None:
        raise RuntimeError("Neo4jService not initialized. Call init_neo4j_service() first.")
    return _neo4j_service