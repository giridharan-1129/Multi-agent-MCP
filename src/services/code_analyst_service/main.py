"""
Code Analyst Service - MCP Server for code analysis and pattern detection.

Responsibilities:
- Analyze function implementations
- Analyze class structures
- Detect design patterns
- Extract code snippets with context
- Compare implementations
"""

import os
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException

from ...shared.mcp_server import BaseMCPServer, ToolResult
from ...shared.neo4j_service import Neo4jService
from ...shared.logger import get_logger

logger = get_logger(__name__)


class CodeAnalystService(BaseMCPServer):
    """MCP Server for code analysis operations."""
    
    def __init__(self):
        super().__init__(
            service_name="CodeAnalystService",
            host=os.getenv("CODE_ANALYST_HOST", "0.0.0.0"),
            port=int(os.getenv("CODE_ANALYST_PORT", 8004))
        )
        self.neo4j_service: Neo4jService = None
    
    async def register_tools(self):
        """Register code analysis tools."""
        
        # Tool 1: Analyze Function
        self.register_tool(
            name="analyze_function",
            description="Deep analysis of a function's logic and calls",
            input_schema={
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Function name to analyze"
                    }
                },
                "required": ["name"]
            },
            handler=self.analyze_function_handler
        )
        
        # Tool 2: Analyze Class
        self.register_tool(
            name="analyze_class",
            description="Comprehensive class analysis including methods and inheritance",
            input_schema={
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Class name to analyze"
                    }
                },
                "required": ["name"]
            },
            handler=self.analyze_class_handler
        )
        
        # Tool 3: Find Patterns
        self.register_tool(
            name="find_patterns",
            description="Detect design patterns in code",
            input_schema={
                "type": "object",
                "properties": {
                    "pattern_type": {
                        "type": "string",
                        "description": "Pattern type to search for (e.g., Singleton, Factory, Decorator)"
                    }
                }
            },
            handler=self.find_patterns_handler
        )
        
        # Tool 4: Get Code Snippet
        self.register_tool(
            name="get_code_snippet",
            description="Extract code with surrounding context",
            input_schema={
                "type": "object",
                "properties": {
                    "entity_name": {
                        "type": "string",
                        "description": "Entity name to get code for"
                    },
                    "context_lines": {
                        "type": "integer",
                        "description": "Lines of context before/after (default: 5)"
                    }
                },
                "required": ["entity_name"]
            },
            handler=self.get_code_snippet_handler
        )
        
        # Tool 5: Compare Implementations
        self.register_tool(
            name="compare_implementations",
            description="Compare two code entities side-by-side",
            input_schema={
                "type": "object",
                "properties": {
                    "entity1": {
                        "type": "string",
                        "description": "First entity name"
                    },
                    "entity2": {
                        "type": "string",
                        "description": "Second entity name"
                    }
                },
                "required": ["entity1", "entity2"]
            },
            handler=self.compare_implementations_handler
        )
        
        # Tool 6: Explain Implementation
        self.register_tool(
            name="explain_implementation",
            description="Generate explanation of how code works",
            input_schema={
                "type": "object",
                "properties": {
                    "entity_name": {
                        "type": "string",
                        "description": "Entity name to explain"
                    }
                },
                "required": ["entity_name"]
            },
            handler=self.explain_implementation_handler
        )
        
        self.logger.info("Registered 6 code analysis tools")
    
    async def _setup_service(self):
        """Initialize Neo4j service."""
        try:
            neo4j_uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
            neo4j_user = os.getenv("NEO4J_USER", "neo4j")
            neo4j_password = os.getenv("NEO4J_PASSWORD", "password")
            
            self.neo4j_service = Neo4jService(neo4j_uri, neo4j_user, neo4j_password)
            await self.neo4j_service.verify_connection()
            
            self.logger.info("Code Analyst Service initialized successfully")
        except Exception as e:
            self.logger.error(f"Failed to initialize code analyst service: {e}")
            raise
    
    # ============================================================================
    # TOOL HANDLERS
    # ============================================================================
    
    async def analyze_function_handler(self, name: str) -> ToolResult:
        """Handle analyze_function tool."""
        try:
            query = """
            MATCH (f:Function {name: $name})
            OPTIONAL MATCH (f)-[:CALLS]->(called)
            OPTIONAL MATCH (caller)-[:CALLS]->(f)
            OPTIONAL MATCH (f)-[:HAS_PARAMETER]->(param)
            RETURN f, collect(distinct called.name) as calls, 
                   collect(distinct caller.name) as callers,
                   collect(distinct param.name) as parameters
            """
            
            result = await self.neo4j_service.execute_query(query, {"name": name})
            
            if not result:
                return ToolResult(success=False, error=f"Function not found: {name}")
            
            record = result[0]
            func = record[0]
            
            return ToolResult(
                success=True,
                data={
                    "name": func.get("name"),
                    "docstring": func.get("docstring", ""),
                    "calls": record[1] or [],
                    "callers": record[2] or [],
                    "parameters": record[3] or [],
                    "complexity": func.get("complexity", "unknown"),
                    "line_count": func.get("line_count", 0)
                }
            )
        except Exception as e:
            self.logger.error(f"Failed to analyze function: {e}")
            return ToolResult(success=False, error=str(e))
    
    async def analyze_class_handler(self, name: str) -> ToolResult:
        """Handle analyze_class tool."""
        try:
            query = """
            MATCH (c:Class {name: $name})
            OPTIONAL MATCH (c)-[:CONTAINS]->(method:Function)
            OPTIONAL MATCH (c)-[:INHERITS_FROM]->(parent)
            OPTIONAL MATCH (child)-[:INHERITS_FROM]->(c)
            OPTIONAL MATCH (c)-[:HAS_PARAMETER]->(attr)
            RETURN c, collect(distinct method.name) as methods,
                   collect(distinct parent.name) as parents,
                   collect(distinct child.name) as subclasses,
                   collect(distinct attr.name) as attributes
            """
            
            result = await self.neo4j_service.execute_query(query, {"name": name})
            
            if not result:
                return ToolResult(success=False, error=f"Class not found: {name}")
            
            record = result[0]
            cls = record[0]
            
            return ToolResult(
                success=True,
                data={
                    "name": cls.get("name"),
                    "docstring": cls.get("docstring", ""),
                    "methods": record[1] or [],
                    "parents": record[2] or [],
                    "subclasses": record[3] or [],
                    "attributes": record[4] or [],
                    "line_count": cls.get("line_count", 0)
                }
            )
        except Exception as e:
            self.logger.error(f"Failed to analyze class: {e}")
            return ToolResult(success=False, error=str(e))
    
    async def find_patterns_handler(
        self,
        pattern_type: str = None
    ) -> ToolResult:
        """Handle find_patterns tool."""
        try:
            if pattern_type:
                query = """
                MATCH (e {design_pattern: $pattern})
                RETURN e.name as name, e.design_pattern as pattern,
                       labels(e)[0] as type
                LIMIT 20
                """
                params = {"pattern": pattern_type}
            else:
                query = """
                MATCH (e)
                WHERE e.design_pattern IS NOT NULL
                RETURN e.name as name, e.design_pattern as pattern,
                       labels(e)[0] as type
                LIMIT 20
                """
                params = {}
            
            result = await self.neo4j_service.execute_query(query, params)
            
            patterns = [
                {"name": record[0], "pattern": record[1], "type": record[2]}
                for record in result
            ]
            
            return ToolResult(
                success=True,
                data={
                    "pattern_type": pattern_type,
                    "found_patterns": patterns,
                    "count": len(patterns)
                }
            )
        except Exception as e:
            self.logger.error(f"Failed to find patterns: {e}")
            return ToolResult(success=False, error=str(e))
    
    async def get_code_snippet_handler(
        self,
        entity_name: str,
        context_lines: int = 5
    ) -> ToolResult:
        """Handle get_code_snippet tool."""
        try:
            query = """
            MATCH (e {name: $name})
            RETURN e.source_code as code, e.file_path as file,
                   e.start_line as start_line, e.end_line as end_line
            """
            
            result = await self.neo4j_service.execute_query(query, {"name": entity_name})
            
            if not result:
                return ToolResult(success=False, error=f"Entity not found: {entity_name}")
            
            record = result[0]
            
            return ToolResult(
                success=True,
                data={
                    "entity": entity_name,
                    "code": record[0] or "",
                    "file": record[1] or "",
                    "start_line": record[2] or 0,
                    "end_line": record[3] or 0
                }
            )
        except Exception as e:
            self.logger.error(f"Failed to get code snippet: {e}")
            return ToolResult(success=False, error=str(e))
    
    async def compare_implementations_handler(
        self,
        entity1: str,
        entity2: str
    ) -> ToolResult:
        """Handle compare_implementations tool."""
        try:
            query = """
            MATCH (e1 {name: $entity1})
            MATCH (e2 {name: $entity2})
            RETURN e1.name as name1, e1.source_code as code1,
                   e2.name as name2, e2.source_code as code2,
                   labels(e1)[0] as type1, labels(e2)[0] as type2
            """
            
            result = await self.neo4j_service.execute_query(
                query,
                {"entity1": entity1, "entity2": entity2}
            )
            
            if not result:
                return ToolResult(success=False, error="One or both entities not found")
            
            record = result[0]
            
            return ToolResult(
                success=True,
                data={
                    "entity1": {
                        "name": record[0],
                        "code": record[1] or "",
                        "type": record[4]
                    },
                    "entity2": {
                        "name": record[2],
                        "code": record[3] or "",
                        "type": record[5]
                    }
                }
            )
        except Exception as e:
            self.logger.error(f"Failed to compare implementations: {e}")
            return ToolResult(success=False, error=str(e))
    
    async def explain_implementation_handler(
        self,
        entity_name: str
    ) -> ToolResult:
        """Handle explain_implementation tool."""
        try:
            query = """
            MATCH (e {name: $name})
            OPTIONAL MATCH (e)-[:CALLS]->(called)
            OPTIONAL MATCH (e)-[:DEPENDS_ON]->(dep)
            RETURN e.docstring as docstring, e.source_code as code,
                   collect(distinct called.name) as calls,
                   collect(distinct dep.name) as dependencies
            """
            
            result = await self.neo4j_service.execute_query(query, {"name": entity_name})
            
            if not result:
                return ToolResult(success=False, error=f"Entity not found: {entity_name}")
            
            record = result[0]
            
            explanation = f"""
# {entity_name}

## Documentation
{record[0] or "No documentation available"}

## Implementation
{record[1] or "No source code available"}

## Dependencies
- Calls: {', '.join(record[2]) if record[2] else 'None'}
- Depends on: {', '.join(record[3]) if record[3] else 'None'}
            """
            
            return ToolResult(
                success=True,
                data={
                    "entity": entity_name,
                    "explanation": explanation.strip()
                }
            )
        except Exception as e:
            self.logger.error(f"Failed to explain implementation: {e}")
            return ToolResult(success=False, error=str(e))
    
    async def _cleanup_service(self):
        """Cleanup Neo4j connection."""
        if self.neo4j_service:
            await self.neo4j_service.close()


# ============================================================================
# FASTAPI APP
# ============================================================================

app = FastAPI(title="Code Analyst Service", version="1.0.0")
analyst_service: CodeAnalystService = None


@app.on_event("startup")
async def startup():
    """Initialize code analyst service."""
    global analyst_service
    analyst_service = CodeAnalystService()
    await analyst_service.initialize()


@app.on_event("shutdown")
async def shutdown():
    """Cleanup on shutdown."""
    if analyst_service:
        await analyst_service.shutdown()


@app.get("/health")
async def health():
    """Health check endpoint."""
    if not analyst_service:
        raise HTTPException(status_code=503, detail="Service not initialized")
    
    db_healthy = await analyst_service.neo4j_service.verify_connection()
    
    if not db_healthy:
        raise HTTPException(status_code=503, detail="Neo4j connection failed")
    
    return {
        "status": "healthy",
        "service": "CodeAnalystService",
        "neo4j": "ok",
        "tools": len(analyst_service.tools)
    }


@app.get("/tools")
async def get_tools():
    """Get available tools schema."""
    if not analyst_service:
        raise HTTPException(status_code=503, detail="Service not initialized")
    
    return {
        "service": "CodeAnalystService",
        "tools": analyst_service.get_tools_schema()
    }


@app.post("/execute")
async def execute_tool(tool_name: str, tool_input: Dict[str, Any]):
    """Execute a tool."""
    if not analyst_service:
        raise HTTPException(status_code=503, detail="Service not initialized")
    
    result = await analyst_service.execute_tool(tool_name, tool_input)
    return result.dict()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app,
        host=os.getenv("CODE_ANALYST_HOST", "0.0.0.0"),
        port=int(os.getenv("CODE_ANALYST_PORT", 8004))
    )
