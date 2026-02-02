# API Reference

Complete reference for all FastAPI Multi-Agent Repository Chat System endpoints.

## Base URL

```
http://localhost:8000
```

All request examples assume this base URL.

## Status Codes

- 200: Successful request
- 201: Resource created
- 400: Bad request (validation error)
- 404: Resource not found
- 500: Server error
- 503: Service unavailable

## Health and Information Endpoints

### GET /health

Check system health status for all components.

Response:
```json
{
  "status": "healthy",
  "components": {
    "orchestrator": {
      "name": "orchestrator",
      "status": "healthy"
    },
    "indexer": {
      "name": "indexer",
      "status": "healthy"
    },
    "graph_query": {
      "name": "graph_query",
      "status": "healthy"
    },
    "code_analyst": {
      "name": "code_analyst",
      "status": "healthy"
    },
    "neo4j": {
      "status": "healthy",
      "statistics": {
        "nodes": {
          "Package": 1050,
          "File": 1050,
          "Class": 771,
          "Function": 4360
        },
        "relationships": {
          "CONTAINS": 1050,
          "DEFINES": 5131,
          "DECORATED_BY": 603
        }
      }
    }
  },
  "correlation_id": "uuid-string"
}
```

### GET /agents

List all available agents with their tools and descriptions.

Response:
```json
{
  "agents": [
    {
      "name": "orchestrator",
      "description": "Central coordinator for the multi-agent system",
      "tools": [
        {
          "name": "analyze_query",
          "description": "Analyze a user query to determine intent and required agents",
          "category": "orchestration"
        },
        {
          "name": "create_conversation",
          "description": "Create a new conversation session",
          "category": "orchestration"
        }
      ]
    }
  ],
  "correlation_id": "uuid-string"
}
```

## Chat Endpoints

### POST /api/chat

Synchronous chat endpoint for sending queries and receiving responses.

Request body:
```json
{
  "query": "What is the FastAPI Request class?",
  "session_id": "optional-uuid-string"
}
```

Parameters:
- query (string, required): The user query
- session_id (string, optional): Session ID for context persistence

Response:
```json
{
  "session_id": "uuid-string",
  "response": "The FastAPI Request class is a wrapper...",
  "agents_used": ["orchestrator", "graph_query"],
  "correlation_id": "uuid-string"
}
```

Status codes:
- 200: Success
- 400: Invalid query format
- 500: Processing error

Example:
```bash
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Explain parameter validation",
    "session_id": "my-session-123"
  }'
```

### WebSocket /ws/chat

Real-time streaming chat using WebSocket protocol.

Connection:
```javascript
const ws = new WebSocket('ws://localhost:8000/ws/chat');
```

Send message:
```json
{
  "query": "How does FastAPI handle authentication?",
  "session_id": "optional-session-id"
}
```

Receive messages (streaming):

Message type: session_created
```json
{
  "type": "session_created",
  "session_id": "uuid-string",
  "correlation_id": "uuid-string"
}
```

Message type: thinking
```json
{
  "type": "thinking",
  "message": "Analyzing query...",
  "correlation_id": "uuid-string"
}
```

Message type: analysis
```json
{
  "type": "analysis",
  "intent": "explanation",
  "entities": ["FastAPI", "authentication"],
  "agents_to_use": ["orchestrator", "code_analyst"],
  "correlation_id": "uuid-string"
}
```

Message type: response_chunk
```json
{
  "type": "response_chunk",
  "chunk": "FastAPI provides multiple authentication methods...",
  "correlation_id": "uuid-string"
}
```

Message type: response_complete
```json
{
  "type": "response_complete",
  "session_id": "uuid-string",
  "agents_used": ["orchestrator", "code_analyst"],
  "correlation_id": "uuid-string"
}
```

Example (Python):
```python
import asyncio
import json
import websockets

async def chat():
    async with websockets.connect("ws://localhost:8000/ws/chat") as ws:
        await ws.send(json.dumps({
            "query": "Explain dependency injection"
        }))
        
        while True:
            msg = await ws.recv()
            data = json.loads(msg)
            print(f"[{data['type']}] {data}")
            
            if data['type'] == 'response_complete':
                break

asyncio.run(chat())
```

## Indexing Endpoints

### POST /api/index

Start asynchronous repository indexing job.

Request body:
```json
{
  "repo_url": "https://github.com/tiangolo/fastapi",
  "full_index": true
}
```

Parameters:
- repo_url (string, required): GitHub repository URL
- full_index (boolean, optional): Whether to index entire repository (default: true)

Response:
```json
{
  "job_id": "uuid-string",
  "status": "pending",
  "repo_url": "https://github.com/tiangolo/fastapi",
  "created_at": "2026-01-30T13:05:25.600448",
  "correlation_id": "uuid-string"
}
```

Status codes:
- 200: Job created
- 400: Invalid repository URL
- 500: Job creation failed

Example:
```bash
curl -X POST http://localhost:8000/api/index \
  -H "Content-Type: application/json" \
  -d '{
    "repo_url": "https://github.com/tiangolo/fastapi",
    "full_index": true
  }'
```

### GET /api/index/jobs/{job_id}

Get status of a specific indexing job.

Path parameters:
- job_id (string, required): Job ID from POST /api/index

Response:
```json
{
  "job_id": "uuid-string",
  "status": "running",
  "progress": 45.5,
  "files_processed": 452,
  "entities_created": 1250,
  "relationships_created": 3400,
  "error": null,
  "correlation_id": "uuid-string"
}
```

Status values:
- pending: Waiting to start
- running: Currently indexing
- completed: Successfully finished
- failed: Indexing failed

Status codes:
- 200: Job found
- 404: Job not found
- 500: Query failed

Example:
```bash
curl http://localhost:8000/api/index/jobs/abc123def456
```

### GET /api/index/jobs

List all indexing jobs with optional filtering.

Query parameters:
- status (string, optional): Filter by status (pending, running, completed, failed)

Response:
```json
{
  "jobs": [
    {
      "id": "uuid-string",
      "status": "completed",
      "repo_url": "https://github.com/tiangolo/fastapi",
      "created_at": "2026-01-30T13:05:25.600448",
      "progress": 100,
      "files_processed": 1050,
      "entities_created": 6081,
      "relationships_created": 9134,
      "error": null
    }
  ],
  "count": 1,
  "correlation_id": "uuid-string"
}
```

Example:
```bash
# Get all jobs
curl http://localhost:8000/api/index/jobs

# Get only running jobs
curl http://localhost:8000/api/index/jobs?status=running
```

### GET /api/index/status

Get current knowledge graph statistics.

Response:
```json
{
  "status": "ok",
  "statistics": {
    "nodes": {
      "Package": 1050,
      "File": 1050,
      "Class": 771,
      "Function": 4360
    },
    "relationships": {
      "CONTAINS": 1050,
      "DEFINES": 5131,
      "DECORATED_BY": 603
    }
  },
  "correlation_id": "uuid-string"
}
```

Example:
```bash
curl http://localhost:8000/api/index/status
```

## Query Endpoints

### POST /api/query/find

Find entities in the knowledge graph by name and optional type.

Query parameters:
- name (string, required): Entity name to search for
- entity_type (string, optional): Filter by type (Class, Function, Module)

Response:
```json
{
  "entity": {
    "name": "HTTPException",
    "type": "Class",
    "module": "fastapi.exceptions",
    "line_number": 45,
    "properties": {}
  },
  "correlation_id": "uuid-string"
}
```

Status codes:
- 200: Entity found
- 404: Entity not found
- 500: Query failed

Example:
```bash
curl -X POST http://localhost:8000/api/query/find \
  -H "Content-Type: application/json" \
  -d '{"name": "HTTPException"}'
```

### POST /api/query/dependencies

Get dependencies of a specified entity.

Query parameters:
- name (string, required): Entity name

Response:
```json
{
  "entity": "HTTPException",
  "dependencies": [
    {"name": "Exception", "type": "Class"},
    {"name": "status", "type": "Variable"}
  ],
  "count": 2,
  "correlation_id": "uuid-string"
}
```

Example:
```bash
curl -X POST http://localhost:8000/api/query/dependencies \
  -H "Content-Type: application/json" \
  -d '{"name": "HTTPException"}'
```

### POST /api/query/dependents

Get entities that depend on the specified entity.

Query parameters:
- name (string, required): Entity name

Response:
```json
{
  "entity": "HTTPException",
  "dependents": [
    {"name": "exception_handler", "type": "Function"},
    {"name": "error_response", "type": "Function"}
  ],
  "count": 2,
  "correlation_id": "uuid-string"
}
```

Example:
```bash
curl -X POST http://localhost:8000/api/query/dependents \
  -H "Content-Type: application/json" \
  -d '{"name": "HTTPException"}'
```

### POST /api/query/related

Get entities related by a specific relationship type.

Query parameters:
- name (string, required): Entity name
- relationship (string, optional): Relationship type filter

Response:
```json
{
  "entity": "fastapi",
  "related": [
    {"name": "starlette", "relationship": "IMPORTS"},
    {"name": "typing", "relationship": "IMPORTS"}
  ],
  "correlation_id": "uuid-string"
}
```

Example:
```bash
curl -X POST http://localhost:8000/api/query/related \
  -H "Content-Type: application/json" \
  -d '{"name": "fastapi", "relationship": "IMPORTS"}'
```

### POST /api/query/execute

Execute custom Cypher query against Neo4j (advanced use).

Request body:
```json
{
  "query": "MATCH (n:Function) WHERE n.name = $name RETURN n LIMIT 5",
  "params": {"name": "get_query"}
}
```

Parameters:
- query (string, required): Cypher query string
- params (object, optional): Query parameters

Response:
```json
{
  "result": [
    {"name": "get_query", "type": "Function", "module": "fastapi"},
    {"name": "get_query_class", "type": "Class", "module": "fastapi"}
  ],
  "correlation_id": "uuid-string"
}
```

Status codes:
- 200: Query executed
- 400: Invalid Cypher syntax
- 500: Query execution error

Example:
```bash
curl -X POST http://localhost:8000/api/query/execute \
  -H "Content-Type: application/json" \
  -d '{
    "query": "MATCH (p:Package) RETURN p.name LIMIT 10",
    "params": {}
  }'
```

## Analysis Endpoints

### POST /api/analysis/function

Analyze a function implementation including signature and usage.

Query parameters:
- name (string, required): Function name
- module (string, optional): Module filter

Response:
```json
{
  "analysis": {
    "name": "get_path",
    "signature": "def get_path(path: str)",
    "docstring": "Get URL path...",
    "calls": ["validate_path", "parse_path"],
    "called_by": ["route_handler"],
    "decorators": ["deprecated"]
  },
  "correlation_id": "uuid-string"
}
```

Example:
```bash
curl -X POST http://localhost:8000/api/analysis/function \
  -H "Content-Type: application/json" \
  -d '{"name": "get_path"}'
```

### POST /api/analysis/class

Analyze class structure including inheritance and methods.

Query parameters:
- name (string, required): Class name
- module (string, optional): Module filter

Response:
```json
{
  "analysis": {
    "name": "Request",
    "base_classes": ["ASGIRequest"],
    "methods": ["__init__", "method", "url", "path"],
    "properties": ["headers", "cookies"],
    "docstring": "HTTP request..."
  },
  "correlation_id": "uuid-string"
}
```

Example:
```bash
curl -X POST http://localhost:8000/api/analysis/class \
  -H "Content-Type: application/json" \
  -d '{"name": "Request"}'
```

### POST /api/analysis/patterns

Detect design patterns in specified code scope.

Query parameters:
- scope (string, optional): Code scope to analyze
- pattern_type (string, optional): Pattern type filter

Response:
```json
{
  "patterns": [
    {
      "type": "singleton",
      "location": "fastapi.FastAPI",
      "description": "Single application instance"
    },
    {
      "type": "decorator",
      "location": "fastapi.routing",
      "description": "Decorator pattern usage"
    }
  ],
  "count": 2,
  "correlation_id": "uuid-string"
}
```

Example:
```bash
curl -X POST http://localhost:8000/api/analysis/patterns \
  -H "Content-Type: application/json" \
  -d '{"scope": "fastapi"}'
```

### POST /api/analysis/compare

Compare implementations of two entities.

Query parameters:
- entity1 (string, required): First entity name
- entity2 (string, required): Second entity name

Response:
```json
{
  "comparison": {
    "entity1": "HTTPException",
    "entity2": "ValidationError",
    "similarities": ["Both inherit from Exception"],
    "differences": [
      "HTTPException has status_code field",
      "ValidationError has detail field"
    ]
  },
  "correlation_id": "uuid-string"
}
```

Example:
```bash
curl -X POST http://localhost:8000/api/analysis/compare \
  -H "Content-Type: application/json" \
  -d '{"entity1": "HTTPException", "entity2": "ValidationError"}'
```

## Error Responses

All endpoints return error responses in this format:

```json
{
  "detail": "Error description",
  "correlation_id": "uuid-string"
}
```

Common errors:

404 Not Found:
```json
{
  "detail": "Job abc123 not found",
  "correlation_id": "uuid-string"
}
```

400 Bad Request:
```json
{
  "detail": "Invalid repository URL format",
  "correlation_id": "uuid-string"
}
```

500 Server Error:
```json
{
  "detail": "Internal server error: Neo4j connection failed",
  "correlation_id": "uuid-string"
}
```

## Correlation IDs

Every request/response includes a correlation_id for tracing. Use this ID when investigating issues:

```bash
grep "correlation_id" /path/to/logs | grep "your-correlation-id"
```

## Rate Limiting

Currently no rate limiting is enforced. Production deployments should implement limits.

## Authentication

No authentication is required. Production deployments should implement API key authentication.

## Pagination

Query results are returned as arrays without pagination. Implement server-side limit/offset in Cypher queries for large result sets.

## Content Types

All endpoints:
- Accept: application/json
- Return: application/json

WebSocket:
- Connection: ws://localhost:8000/ws/chat
- Message format: JSON strings

## Examples

See QUICK_START.md for practical examples of using these endpoints.

Full interactive documentation available at: http://localhost:8000/docs