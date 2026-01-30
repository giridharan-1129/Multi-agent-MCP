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
        """Connect to Neo4j."""
        try:
            from neo4j import GraphDatabase
            
            self.driver = GraphDatabase.driver(
                self.uri,
                auth=(self.username, self.password)
            )
            
            # Test connection
            with self.driver.session(database=self.database) as session:
                session.run("RETURN 1")
            
            logger.info(f"Connected to Neo4j: {self.uri}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to connect to Neo4j: {str(e)}")
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
                import os
                filename = os.path.basename(path)
                
                session.run(
                    """
                    MERGE (f:File {path: $path})
                    SET f.name = $name
                    """,
                    {"path": path, "name": filename},
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
            with self.driver.session(database=self.database) as session:
                session.run(
                    f"""
                    MATCH (a:{source_label} {{name: $source}})
                    MATCH (b:{target_label} {{name: $target}})
                    MERGE (a)-[r:{rel_type}]->(b)
                    SET r += $props
                    """,
                    {
                        "source": source_name,
                        "target": target_name,
                        "props": properties or {},
                    },
                )

        await run_in_threadpool(_run)



    async def create_defines_relationship(
        self,
        file_path: str,
        target_name: str,
        target_module: str,
        target_type: str,
    ):
        def _run():
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
                    # 1️⃣ Exact match (case-insensitive)
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

                    # 2️⃣ Fallback: contains
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

 