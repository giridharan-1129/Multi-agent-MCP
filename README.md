# FastAPI Multi-Agent Repository Chat System

A production-ready multi-agent system for analyzing GitHub repositories using the Model Context Protocol (MCP). Built with FastAPI, Neo4j, and OpenAI.

## 🎯 Overview

This system provides intelligent code analysis through specialized agents:

- **Orchestrator Agent**: Routes queries to appropriate agents, manages conversation context
- **Indexer Agent**: Downloads and indexes repositories into a Neo4j knowledge graph
- **Graph Query Agent**: Queries the knowledge graph for entities and relationships
- **Code Analyst Agent**: Analyzes code patterns, identifies design patterns, compares implementations

## 🏗️ Architecture
```
┌─────────────────────────────────────────────────────────────┐
│                     FastAPI Gateway                          │
│              (REST API Entry Point - Port 8000)             │
└────────────┬──────────────────────────────────────────────┘
             │
             ├──────────────────────────────────────────┐
             │                                          │
    ┌────────▼────────┐  ┌──────────────┐  ┌─────────────────┐
    │  Orchestrator   │  │   Indexer    │  │  GraphQuery     │
    │     Agent       │  │    Agent     │  │     Agent       │
    │   (Port 8001)   │  │  (Port 8002) │  │   (Port 8003)   │
    └────────┬────────┘  └──────┬───────┘  └────────┬────────┘
             │                  │                   │
             └──────────────────┼───────────────────┘
                                │
                    ┌───────────▼──────────┐
                    │   CodeAnalyst Agent  │
                    │     (Port 8004)      │
                    └───────────┬──────────┘
                                │
                    ┌───────────▼──────────┐
                    │   Neo4j Database     │
                    │  Knowledge Graph     │
                    │   (Port 7687)        │
                    └──────────────────────┘
```

## 📋 Requirements

- Python 3.10+
- Docker & Docker Compose (for Neo4j)
- OpenAI API key
- Git

## 🚀 Quick Start

### 1. Setup Environment
```bash
# Clone or navigate to project directory
cd MultiAgentMCP

# Create .env file from template
cp .env.example .env

# Edit .env with your credentials
# - Add your OpenAI API key
# - Set Neo4j password
# - Adjust other settings as needed
nano .env
```

### 2. Install Dependencies
```bash
# Install Python dependencies
pip install -e .

# Or with development dependencies
pip install -e ".[dev]"
```

### 3. Start Neo4j Database
```bash
# Using Docker
docker run -d \
  --name neo4j \
  -p 7687:7687 \
  -p 7474:7474 \
  -e NEO4J_AUTH=neo4j/password \
  neo4j:5.14

# Or using Docker Compose
docker-compose up -d neo4j
```

### 4. Start the Gateway
```bash
# Development mode
uvicorn src.gateway.main:app --reload --host 0.0.0.0 --port 8000

# Production mode
uvicorn src.gateway.main:app --host 0.0.0.0 --port 8000 --workers 4
```

### 5. Access the API
```bash
# Health check
curl http://localhost:8000/health

# API Documentation
# Swagger UI: http://localhost:8000/docs
# ReDoc: http://localhost:8000/redoc
```

## 📚 API Endpoints

### Health & Info

- `GET /health` - System health check
- `GET /agents` - List all available agents

### Chat

- `POST /api/chat` - Chat with the system
```json
  {
    "query": "How does FastAPI handle dependency injection?",
    "session_id": "optional-session-id"
  }
```

### Repository Indexing

- `POST /api/index` - Index a GitHub repository
```json
  {
    "repo_url": "https://github.com/tiangolo/fastapi",
    "full_index": true
  }
```
- `GET /api/index/status` - Get indexing statistics

### Entity Queries

- `POST /api/query/find?name=FastAPI&entity_type=Class` - Find entity
- `POST /api/query/dependencies?name=APIRouter` - Get dependencies
- `POST /api/analysis/function?name=get_openapi_schema` - Analyze function

## 🔧 Configuration

All configuration is managed through environment variables in `.env`:

### Database
```
NEO4J_URI=bolt://localhost:7687
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=your-secure-password
```

### OpenAI
```
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4
OPENAI_TEMPERATURE=0.7
```

### Gateway
```
GATEWAY_HOST=0.0.0.0
GATEWAY_PORT=8000
GATEWAY_RELOAD=true
```

### Logging
```
LOG_LEVEL=INFO
LOG_FORMAT=json
```

## 🧪 Testing
```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=src --cov-report=html

# Run specific test file
pytest tests/test_ast_parser.py

# Run specific test
pytest tests/test_neo4j_service.py::test_connect
```

## 📊 Knowledge Graph Schema

### Nodes

- **Module**: Python files
- **Class**: Class definitions
- **Function**: Function/method definitions

### Relationships

- **INHERITS_FROM**: Class inheritance
- **IMPORTS**: Module imports
- **CALLS**: Function calls
- **DECORATED_BY**: Decorator usage
- **HAS_PARAMETER**: Function parameters
- **CONTAINS**: Module contains entity

## 🔍 Example Queries

### Index FastAPI
```bash
curl -X POST http://localhost:8000/api/index \
  -H "Content-Type: application/json" \
  -d '{
    "repo_url": "https://github.com/tiangolo/fastapi",
    "full_index": true
  }'
```

### Find an Entity
```bash
curl -X POST "http://localhost:8000/api/query/find?name=FastAPI&entity_type=Class"
```

### Get Dependencies
```bash
curl -X POST "http://localhost:8000/api/query/dependencies?name=APIRouter"
```

### Chat
```bash
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d '{
    "query": "How does FastAPI handle request validation?"
  }'
```

## 🏢 Production Deployment

### Docker Compose
```bash
# Build and start all services
docker-compose up -d

# View logs
docker-compose logs -f

# Stop services
docker-compose down
```

### Environment-Specific Config
```bash
# Development
ENVIRONMENT=development LOG_LEVEL=DEBUG

# Production
ENVIRONMENT=production LOG_LEVEL=INFO GATEWAY_RELOAD=false
```

## 📝 Project Structure
```
MultiAgentMCP/
├── src/
│   ├── agents/                 # MCP Agents
│   │   ├── orchestrator_agent.py
│   │   ├── indexer_agent.py
│   │   ├── graph_query_agent.py
│   │   └── code_analyst_agent.py
│   ├── gateway/                # FastAPI Gateway
│   │   └── main.py
│   └── shared/                 # Shared modules
│       ├── config.py
│       ├── logger.py
│       ├── exceptions.py
│       ├── mcp_types.py
│       ├── neo4j_service.py
│       ├── repo_downloader.py
│       ├── ast_parser.py
│       ├── relationship_builder.py
│       └── base_agent.py
├── tests/                      # Test suite
├── docker/                     # Docker configuration
├── config/                     # Configuration files
├── .env.example               # Environment template
├── pyproject.toml             # Project metadata
└── README.md                  # This file
```

## 🐛 Troubleshooting

### Neo4j Connection Failed
```bash
# Check if Neo4j is running
docker ps | grep neo4j

# Check Neo4j logs
docker logs neo4j

# Restart Neo4j
docker restart neo4j
```

### Import Errors
```bash
# Reinstall dependencies
pip install -e . --force-reinstall

# Check Python path
python -c "import sys; print(sys.path)"
```

### OpenAI API Errors
```bash
# Verify API key is set
echo $OPENAI_API_KEY

# Check API key is valid
curl https://api.openai.com/v1/models \
  -H "Authorization: Bearer $OPENAI_API_KEY"
```

## 📈 Monitoring

### Health Checks
```bash
# Full health check
curl http://localhost:8000/health | jq

# List agents
curl http://localhost:8000/agents | jq
```

### Logs

Logs are structured JSON format for easy parsing:
```bash
# View logs with jq
docker logs gateway | jq .correlation_id
```

## 🤝 Contributing

1. Create a feature branch: `git checkout -b feature/my-feature`
2. Make changes and add tests
3. Run tests: `pytest`
4. Commit: `git commit -am 'Add feature'`
5. Push: `git push origin feature/my-feature`
6. Create Pull Request

## 📄 License

MIT License - see LICENSE file for details

## 🙋 Support

For issues and questions:
1. Check existing issues on GitHub
2. Create a new issue with details
3. Include logs and error messages

## 🎓 Learning Resources

- [MCP Documentation](https://modelcontextprotocol.io/)
- [FastAPI Tutorial](https://fastapi.tiangolo.com/)
- [Neo4j Cypher Guide](https://neo4j.com/developer/cypher/)
- [FastAPI Repository](https://github.com/tiangolo/fastapi)

## 📞 Contact

Built as an interview assignment for AI Engineer role.

---

**Happy coding! 🚀**
