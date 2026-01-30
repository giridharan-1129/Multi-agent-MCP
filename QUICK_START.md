# Quick Start Guide

Get the FastAPI Multi-Agent Repository Chat System running in 5 minutes.

## Prerequisites

- Docker and Docker Compose installed
- Git installed
- Basic understanding of REST APIs and WebSockets

## 1. Clone and Configure (2 minutes)

Clone the repository:
```bash
git clone <repository-url>
cd MultiAgentMCP
```

Set up environment variables:
```bash
cp .env.example .env
```

Edit .env and set required variables:
```
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=your-secure-password
OPENAI_API_KEY=your-openai-key
```

## 2. Start the System (3 minutes)

Start all services:
```bash
docker-compose up -d
```

Verify services are running:
```bash
docker-compose ps
```

You should see:
- multiagent-neo4j: Up
- multiagent-gateway: Up

## 3. Verify Installation

Check system health:
```bash
curl http://localhost:8000/health
```

Expected response:
```json
{
  "status": "healthy",
  "components": {
    "orchestrator": {"status": "healthy"},
    "indexer": {"status": "healthy"},
    "graph_query": {"status": "healthy"},
    "code_analyst": {"status": "healthy"},
    "neo4j": {"status": "healthy"}
  }
}
```

Access API documentation:
```
http://localhost:8000/docs
```

## 4. Test Basic Functionality

Test REST chat API:
```bash
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"query":"What is FastAPI?"}'
```

Test WebSocket chat:
```python
import asyncio
import json
import websockets

async def test_websocket():
    async with websockets.connect("ws://localhost:8000/ws/chat") as ws:
        await ws.send(json.dumps({"query": "Explain dependency injection"}))
        
        for _ in range(5):
            msg = await asyncio.wait_for(ws.recv(), timeout=5)
            data = json.loads(msg)
            print(f"Received: {data.get('type')}")
            
            if data.get('type') == 'response_complete':
                break

asyncio.run(test_websocket())
```

List available agents:
```bash
curl http://localhost:8000/agents | python3 -m json.tool | head -30
```

## 5. Index a Repository

Start indexing the FastAPI repository:
```bash
curl -X POST http://localhost:8000/api/index \
  -H "Content-Type: application/json" \
  -d '{
    "repo_url": "https://github.com/tiangolo/fastapi",
    "full_index": true
  }'
```

This returns a job_id. Store it to track progress:
```json
{
  "job_id": "abc123def456",
  "status": "pending",
  "repo_url": "https://github.com/tiangolo/fastapi",
  "created_at": "2026-01-30T13:05:25.600448"
}
```

Check job status:
```bash
curl http://localhost:8000/api/index/jobs/abc123def456
```

Response shows current progress:
```json
{
  "job_id": "abc123def456",
  "status": "running",
  "progress": 45.5,
  "files_processed": 452,
  "entities_created": 1250,
  "relationships_created": 3400
}
```

View graph statistics:
```bash
curl http://localhost:8000/api/index/status
```

## 6. Query the Knowledge Graph

Find a function:
```bash
curl -X POST http://localhost:8000/api/query/find \
  -H "Content-Type: application/json" \
  -d '{"name": "HTTPException"}'
```

Get dependencies:
```bash
curl -X POST http://localhost:8000/api/query/dependencies \
  -H "Content-Type: application/json" \
  -d '{"name": "HTTPException"}'
```

## Common Tasks

### View Logs

Check gateway logs:
```bash
docker-compose logs -f gateway
```

Check Neo4j logs:
```bash
docker-compose logs -f neo4j
```

### Stop the System

Stop all containers:
```bash
docker-compose down
```

To also remove data:
```bash
docker-compose down -v
```

### Restart the System

Restart all services:
```bash
docker-compose restart
```

### Access Neo4j Browser

Open browser to: http://localhost:7475

Login with credentials from .env file

Query example:
```cypher
MATCH (p:Package) RETURN p.name LIMIT 10
```

### Local Development

For development without Docker:

1. Install dependencies:
```bash
python3 -m venv venv
source venv/bin/activate
pip install -e ".[dev]"
```

2. Start Neo4j separately:
```bash
docker run -d \
  --name neo4j \
  -p 7687:7687 \
  -e NEO4J_AUTH=neo4j/password \
  neo4j:5.14-community
```

3. Start gateway:
```bash
uvicorn src.gateway.main:app --reload --host 0.0.0.0 --port 8000
```

4. Run tests:
```bash
pytest src/tests/ -v --cov=src
```

## Troubleshooting

### Services not starting

Check docker-compose.yml syntax:
```bash
docker-compose config
```

View detailed logs:
```bash
docker-compose up --no-detach
```

### Neo4j connection errors

Verify Neo4j is healthy:
```bash
curl http://localhost:7474
```

Check Neo4j logs:
```bash
docker-compose logs neo4j
```

### Gateway not responding

Check if container is running:
```bash
docker-compose ps gateway
```

View gateway logs:
```bash
docker-compose logs gateway
```

Verify port is not in use:
```bash
lsof -i :8000
```

### Out of memory

Neo4j and gateway may need memory allocation. Edit docker-compose.yml:

```yaml
gateway:
  # Add:
  deploy:
    resources:
      limits:
        memory: 2G
```

### Permission denied errors

Ensure Docker daemon is running:
```bash
sudo systemctl start docker
```

Or add user to docker group:
```bash
sudo usermod -aG docker $USER
```

## Next Steps

1. Read the full README.md for complete documentation
2. Review API.md for endpoint reference
3. Check ARCHITECTURE.md for design details
4. Explore the codebase in src/
5. Run tests to verify functionality

## API Quick Reference

Health: GET /health
Agents: GET /agents
Chat: POST /api/chat
WebSocket: WS /ws/chat
Index: POST /api/index
Job Status: GET /api/index/jobs/{id}
Graph Stats: GET /api/index/status
Find: POST /api/query/find
Dependencies: POST /api/query/dependencies
Analyze Function: POST /api/analysis/function

Full documentation at: http://localhost:8000/docs

## Support

For issues:
1. Check docker-compose logs
2. Verify .env configuration
3. Ensure ports are available (8000, 7687, 7474)
4. Review README.md troubleshooting section
5. Check API documentation at /docs endpoint