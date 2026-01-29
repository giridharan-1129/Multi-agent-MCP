"""
Neo4j Database Service.

Handles all Neo4j database operations for the knowledge graph.
"""

from typing import Any, Dict, List, Optional
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

    async def execute_query(self, query: str, params: Optional[Dict] = None) -> List[Dict]:
        """Execute a Cypher query."""
        try:
            if not self.driver:
                return []
            
            with self.driver.session(database=self.database) as session:
                result = session.run(query, params or {})
                return [dict(record) for record in result]
                
        except Exception as e:
            logger.error(f"Query execution failed: {str(e)}")
            return []

    async def find_entity(self, name: str, entity_type: Optional[str] = None):
            """Find an entity by name."""
            try:
                if not self.driver:
                    return {}
                
                query = "MATCH (n) WHERE n.name = $name RETURN n as entity"
                
                with self.driver.session(database=self.database) as session:
                    result = session.run(query, {"name": name})
                    records = [dict(record) for record in result]
                    return {"entity": records[0] if records else None} if records else {}
                    
            except Exception as e:
                logger.error(f"Failed to find entity: {str(e)}")
                return {}

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

 