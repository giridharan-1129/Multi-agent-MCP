"""
Graph Query Service - MCP Server for Neo4j knowledge graph operations.

Responsibilities:
- Execute Cypher queries
- Find entities by name
- Traverse dependency relationships
- Trace import chains
- Find related entities
"""

import os
from typing import Any, Dict, List, Optional
from uuid import UUID

from fastapi import FastAPI, HTTPException
from neo4j import AsyncDriver, asyncio as aioneo4j

from ...shared.mcp_server import BaseMCPServer, ToolResult
from ...shared.neo4j_service import Neo4jService
from ...shared.logger import get_logger

logger = get_logger(__name__)


class GraphQueryService(BaseMCPServer):
    """MCP Server for graph database operations."""
    
    def __init__(self):
        super().__init__(
            service_name="GraphQueryService",
            host=os.getenv("GRAPH_QUERY_HOST", "0.0.0.0"),
            port=int(os.getenv("GRAPH_QUERY_PORT", 8003))
        )
        self.neo4j_service: Neo4jService = None
    
    async def register_tools(self):
        """Register graph query tools."""
        
        # Tool 1: Find Entity
        self.register_tool(
            name="find_entity",
            description="Find a class, function, or module by name",
            input_schema={
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Entity name to search for"
                    },
                    "entity_type": {
                        "type": "string",
                        "enum": ["Class", "Function", "Module"],
                        "description": "Optional filter by entity type"
                    }
                },
                "required": ["name"]
            },
            handler=self.find_entity_handler
        )
        
        # Tool 2: Get Dependencies
        self.register_tool(
            name="get_dependencies",
            description="Find what an entity depends on",
            input_schema={
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Entity name to analyze"
                    }
                },
                "required": ["name"]
            },
            handler=self.get_dependencies_handler
        )
        
        # Tool 3: Get Dependents
        self.register_tool(
            name="get_dependents",
            description="Find what depends on an entity (who uses it)",
            input_schema={
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Entity name to analyze"
                    }
                },
                "required": ["name"]
            },
            handler=self.get_dependents_handler
        )
        
        # Tool 4: Trace Imports
        self.register_tool(
            name="trace_imports",
            description="Follow import chain for a module",
            input_schema={
                "type": "object",
                "properties": {
                    "module_name": {
                        "type": "string",
                        "description": "Module name to trace"
                    }
                },
                "required": ["module_name"]
            },
            handler=self.trace_imports_handler
        )
        
        # Tool 5: Find Related
        self.register_tool(
            name="find_related",
            description="Get entities related by specified relationship type",
            input_schema={
                "type": "object",
                "properties": {
                    "entity_name": {
                        "type": "string",
                        "description": "Starting entity name"
                    },
                    "relationship_type": {
                        "type": "string",
                        "description": "Relationship type (e.g., CALLS, INHERITS_FROM)"
                    },
                    "direction": {
                        "type": "string",
                        "enum": ["outgoing", "incoming", "both"],
                        "description": "Relationship direction"
                    }
                },
                "required": ["entity_name", "relationship_type"]
            },
            handler=self.find_related_handler
        )
        
        # Tool 6: Execute Custom Query
        self.register_tool(
            name="execute_query",
            description="Execute custom Cypher query (read-only, with safety checks)",
            input_schema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Cypher query to execute"
                    },
                    "parameters": {
                        "type": "object",
                        "description": "Query parameters"
                    }
                },
                "required": ["query"]
            },
            handler=self.execute_query_handler
        )
        
        self.logger.info("Registered 6 graph query tools")
    
    async def _setup_service(self):
        """Initialize Neo4j service."""
        try:
            neo4j_uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
            neo4j_user = os.getenv("NEO4J_USER", "neo4j")
            neo4j_password = os.getenv("NEO4J_PASSWORD", "password")
            
            self.neo4j_service = Neo4jService(neo4j_uri, neo4j_user, neo4j_password)
            await self.neo4j_service.verify_connection()
            
            self.logger.info("Graph Query Service initialized successfully")
        except Exception as e:
            self.logger.error(f"Failed to initialize graph query service: {e}")
            raise
    
    # ============================================================================
    # TOOL HANDLERS
    # ============================================================================
    
    async def find_entity_handler(
        self,
        name: str,
        entity_type: str = None
    ) -> ToolResult:
        """Handle find_entity tool."""
        try:
            query = "MATCH (e) WHERE e.name = $name"
            params = {"name": name}
            
            if entity_type:
                query += f" AND '{entity_type}' IN labels(e)"
            
            query += " RETURN e, labels(e) as types LIMIT 1"
            
            result = await self.neo4j_service.execute_query(query, params)
            
            if not result:
                return ToolResult(success=False, error=f"Entity not found: {name}")
            
            record = result[0]
            entity = record[0]
            
            return ToolResult(
                success=True,
                data={
                    "name": entity.get("name"),
                    "type": record[1][0] if record[1] else "Unknown",
                    "properties": dict(entity)
                }
            )
        except Exception as e:
            self.logger.error(f"Failed to find entity: {e}")
            return ToolResult(success=False, error=str(e))
    
    async def get_dependencies_handler(self, name: str) -> ToolResult:
        """Handle get_dependencies tool."""
        try:
            query = """
            MATCH (e {name: $name})-[r:DEPENDS_ON|IMPORTS|CALLS]->(dep)
            RETURN dep.name as dependency, type(r) as relationship_type
            LIMIT 20
            """
            
            result = await self.neo4j_service.execute_query(query, {"name": name})
            
            dependencies = [
                {"name": record[0], "type": record[1]}
                for record in result
            ]
            
            return ToolResult(
                success=True,
                data={
                    "entity": name,
                    "dependencies": dependencies,
                    "count": len(dependencies)
                }
            )
        except Exception as e:
            self.logger.error(f"Failed to get dependencies: {e}")
            return ToolResult(success=False, error=str(e))
    
    async def get_dependents_handler(self, name: str) -> ToolResult:
        """Handle get_dependents tool."""
        try:
            query = """
            MATCH (e {name: $name})<-[r:DEPENDS_ON|IMPORTS|CALLS]-(dependent)
            RETURN dependent.name as dependent, type(r) as relationship_type
            LIMIT 20
            """
            
            result = await self.neo4j_service.execute_query(query, {"name": name})
            
            dependents = [
                {"name": record[0], "type": record[1]}
                for record in result
            ]
            
            return ToolResult(
                success=True,
                data={
                    "entity": name,
                    "dependents": dependents,
                    "count": len(dependents)
                }
            )
        except Exception as e:
            self.logger.error(f"Failed to get dependents: {e}")
            return ToolResult(success=False, error=str(e))
    
    async def trace_imports_handler(self, module_name: str) -> ToolResult:
        """Handle trace_imports tool."""
        try:
            query = """
            MATCH path = (m:Module {name: $module})-[:IMPORTS*]->(imported)
            RETURN [node.name for node in nodes(path)] as import_chain
            LIMIT 5
            """
            
            result = await self.neo4j_service.execute_query(query, {"module": module_name})
            
            chains = [record[0] for record in result]
            
            return ToolResult(
                success=True,
                data={
                    "module": module_name,
                    "import_chains": chains,
                    "count": len(chains)
                }
            )
        except Exception as e:
            self.logger.error(f"Failed to trace imports: {e}")
            return ToolResult(success=False, error=str(e))
    
    async def find_related_handler(
        self,
        entity_name: str,
        relationship_type: str,
        direction: str = "outgoing"
    ) -> ToolResult:
        """Handle find_related tool."""
        try:
            if direction == "outgoing":
                query = f"MATCH (e {{name: $name}})-[:{relationship_type}]->(related) RETURN related.name"
            elif direction == "incoming":
                query = f"MATCH (e {{name: $name}})<-[:{relationship_type}]-(related) RETURN related.name"
            else:  # both
                query = f"MATCH (e {{name: $name}})-[:{relationship_type}]-(related) RETURN related.name"
            
            query += " LIMIT 20"
            
            result = await self.neo4j_service.execute_query(query, {"name": entity_name})
            
            related = [record[0] for record in result]
            
            return ToolResult(
                success=True,
                data={
                    "entity": entity_name,
                    "relationship": relationship_type,
                    "direction": direction,
                    "related": related,
                    "count": len(related)
                }
            )
        except Exception as e:
            self.logger.error(f"Failed to find related: {e}")
            return ToolResult(success=False, error=str(e))
    
    async def execute_query_handler(
        self,
        query: str,
        parameters: Dict[str, Any] = None
    ) -> ToolResult:
        """Handle execute_query tool with safety checks."""
        try:
            # Safety check: disallow write operations
            dangerous_keywords = ["CREATE", "DELETE", "SET", "DROP", "ALTER"]
            if any(keyword in query.upper() for keyword in dangerous_keywords):
                return ToolResult(
                    success=False,
                    error="Write operations not allowed"
                )
            
            result = await self.neo4j_service.execute_query(
                query,
                parameters or {}
            )
            
            return ToolResult(
                success=True,
                data={
                    "results": result,
                    "count": len(result)
                }
            )
        except Exception as e:
            self.logger.error(f"Failed to execute query: {e}")
            return ToolResult(success=False, error=str(e))
    
    async def _cleanup_service(self):
        """Cleanup Neo4j connection."""
        if self.neo4j_service:
            await self.neo4j_service.close()


# ============================================================================
# FASTAPI APP
# ============================================================================

app = FastAPI(title="Graph Query Service", version="1.0.0")
graph_service: GraphQueryService = None


@app.on_event("startup")
async def startup():
    """Initialize graph query service."""
    global graph_service
    graph_service = GraphQueryService()
    await graph_service.initialize()


@app.on_event("shutdown")
async def shutdown():
    """Cleanup on shutdown."""
    if graph_service:
        await graph_service.shutdown()


@app.get("/health")
async def health():
    """Health check endpoint."""
    if not graph_service:
        raise HTTPException(status_code=503, detail="Service not initialized")
    
    db_healthy = await graph_service.neo4j_service.verify_connection()
    
    if not db_healthy:
        raise HTTPException(status_code=503, detail="Neo4j connection failed")
    
    return {
        "status": "healthy",
        "service": "GraphQueryService",
        "neo4j": "ok",
        "tools": len(graph_service.tools)
    }


@app.get("/tools")
async def get_tools():
    """Get available tools schema."""
    if not graph_service:
        raise HTTPException(status_code=503, detail="Service not initialized")
    
    return {
        "service": "GraphQueryService",
        "tools": graph_service.get_tools_schema()
    }


@app.post("/execute")
async def execute_tool(tool_name: str, tool_input: Dict[str, Any]):
    """Execute a tool."""
    if not graph_service:
        raise HTTPException(status_code=503, detail="Service not initialized")
    
    result = await graph_service.execute_tool(tool_name, tool_input)
    return result.dict()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app,
        host=os.getenv("GRAPH_QUERY_HOST", "0.0.0.0"),
        port=int(os.getenv("GRAPH_QUERY_PORT", 8003))
    )
