# Quick Start Guide

Get the FastAPI Multi-Agent System running in 5 minutes!

## Prerequisites

- Python 3.10+
- Docker & Docker Compose
- OpenAI API key (get from https://platform.openai.com/api-keys)
- Git

## 🚀 Option 1: Quick Start with Docker (Easiest)

### Step 1: Clone and Setup
```bash
cd MultiAgentMCP

# Copy environment template
cp .env.example .env

# Edit .env and add your OpenAI API key
nano .env
# Find OPENAI_API_KEY=your-openai-api-key-here
# Replace with your actual key
```

### Step 2: Start Everything
```bash
# Start Neo4j and Gateway
docker-compose up -d

# Wait for services to start (30 seconds)
sleep 30

# Check status
docker-compose ps
```

### Step 3: Verify Setup
```bash
# Check health
curl http://localhost:8000/health | jq

# List agents
curl http://localhost:8000/agents | jq
```

### Step 4: Access the API
```
Swagger UI:    http://localhost:8000/docs
ReDoc:         http://localhost:8000/redoc
API Base:      http://localhost:8000
```

## 🖥️ Option 2: Local Development Setup

### Step 1: Initial Setup
```bash
# Run setup script
./scripts/setup.sh

# This will:
# - Check Python version
# - Create .env file
# - Install dependencies
# - Start Neo4j with Docker
```

### Step 2: Edit Configuration
```bash
# Open and edit .env
nano .env

# Key settings:
OPENAI_API_KEY=sk-...          # Your OpenAI API key
NEO4J_PASSWORD=change-me        # Set a strong password
LOG_LEVEL=DEBUG                 # DEBUG for development
```

### Step 3: Start Gateway
```bash
# Start with auto-reload
uvicorn src.gateway.main:app --reload

# Or use the start script
./scripts/start-dev.sh
```

## 📝 Example API Calls

### 1. Check System Health
```bash
curl http://localhost:8000/health | jq
```

Response:
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

### 2. Index FastAPI Repository
```bash
curl -X POST http://localhost:8000/api/index \
  -H "Content-Type: application/json" \
  -d '{
    "repo_url": "https://github.com/tiangolo/fastapi",
    "full_index": true
  }' | jq
```

Response:
```json
{
  "status": "success",
  "files_processed": 45,
  "entities_created": 320,
  "relationships_created": 580
}
```

### 3. Chat with System
```bash
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{
    "query": "How does FastAPI handle dependency injection?"
  }' | jq
```

### 4. Find an Entity
```bash
curl -X POST "http://localhost:8000/api/query/find?name=FastAPI&entity_type=Class" | jq
```

### 5. Get Dependencies
```bash
curl -X POST "http://localhost:8000/api/query/dependencies?name=APIRouter" | jq
```

### 6. Analyze a Function
```bash
curl -X POST "http://localhost:8000/api/analysis/function?name=get_openapi_schema" | jq
```

## 🐛 Troubleshooting

### Neo4j Connection Failed
```bash
# Check if Neo4j is running
docker ps | grep neo4j

# View Neo4j logs
docker logs neo4j

# Restart Neo4j
docker restart neo4j

# Or start manually
docker run -d \
  --name neo4j \
  -p 7687:7687 \
  -p 7474:7474 \
  -e NEO4J_AUTH=neo4j/password \
  neo4j:5.14
```

### Gateway Won't Start
```bash
# Check if port 8000 is in use
lsof -i :8000

# Kill the process if needed
kill -9 <PID>

# Or use a different port
uvicorn src.gateway.main:app --port 8001
```

### OpenAI API Key Error
```bash
# Verify API key is set
echo $OPENAI_API_KEY

# Test API key
curl https://api.openai.com/v1/models \
  -H "Authorization: Bearer $OPENAI_API_KEY"
```

### Python Version Issue
```bash
# Check Python version
python --version

# Should be 3.10+
# If not, install Python 3.10 or later
```

## 📊 Common Workflows

### Workflow 1: Index and Query
```bash
# 1. Index repository
curl -X POST http://localhost:8000/api/index \
  -H "Content-Type: application/json" \
  -d '{"repo_url": "https://github.com/tiangolo/fastapi"}'

# 2. Wait for indexing to complete (check status)
curl http://localhost:8000/api/index/status

# 3. Find an entity
curl -X POST "http://localhost:8000/api/query/find?name=FastAPI"

# 4. Get its dependencies
curl -X POST "http://localhost:8000/api/query/dependencies?name=FastAPI"
```

### Workflow 2: Chat Conversation
```bash
# 1. Start a chat (no session_id needed for first message)
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{"query": "What is FastAPI?"}'

# Response will include session_id

# 2. Continue conversation with same session
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{
    "query": "Show me examples",
    "session_id": "<session_id_from_above>"
  }'
```

### Workflow 3: Code Analysis
```bash
# 1. Analyze a function
curl -X POST "http://localhost:8000/api/analysis/function?name=get_openapi_schema"

# 2. Analyze a class
curl -X POST "http://localhost:8000/api/analysis/class?name=FastAPI"

# 3. Find design patterns
curl -X POST "http://localhost:8000/api/analysis/patterns"

# 4. Compare implementations
curl -X POST http://localhost:8000/api/analysis/compare \
  -H "Content-Type: application/json" \
  -d '{"entity1": "APIRouter", "entity2": "FastAPI"}'
```

## 🛠️ Useful Commands
```bash
# View logs (Docker)
docker-compose logs -f gateway
docker-compose logs -f neo4j

# Stop all services
docker-compose down

# Stop and remove volumes (clean slate)
docker-compose down -v

# Rebuild images
docker-compose build

# Run tests
make test

# Format code
make format

# Lint code
make lint
```

## 📚 Next Steps

1. Read [README.md](README.md) for full documentation
2. Check [ARCHITECTURE.md](ARCHITECTURE.md) for system design
3. Explore [API endpoints](README.md#-api-endpoints) in detail
4. Run [tests](QUICK_START.md#-option-2-local-development-setup)
5. Index your own repository

## 🆘 Getting Help

- Check the [Troubleshooting section](README.md#-troubleshooting)
- Review logs: `docker-compose logs -f`
- Check API docs: http://localhost:8000/docs
- Review examples in this guide

## ✅ Verification Checklist

After setup, verify everything works:

- [ ] `curl http://localhost:8000/health` returns 200
- [ ] All 4 agents show "healthy" status
- [ ] Can index a repository
- [ ] Can query entities
- [ ] Can perform code analysis
- [ ] Swagger UI loads at `/docs`

**You're ready to go! 🎉**

For detailed information, see [README.md](README.md).
