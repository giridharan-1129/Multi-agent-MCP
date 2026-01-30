# FastAPI Multi-Agent Repository Chat System

## Overview

FastAPI Multi-Agent Repository Chat System is a production-grade distributed system designed to provide intelligent code repository analysis through specialized AI agents. The system indexes GitHub repositories into a Neo4j knowledge graph and provides real-time interfaces for querying code structure, dependencies, and design patterns.

Built with FastAPI, Neo4j, and the Model Context Protocol (MCP), this system demonstrates enterprise-level distributed architecture with clear separation of concerns and scalable design patterns.

## Core Architecture

The system follows a multi-agent architecture where each agent specializes in a specific domain:

- **Orchestrator Agent**: Query analysis, routing, and response synthesis
- **Indexer Agent**: Repository parsing and Neo4j indexing
- **Graph Query Agent**: Knowledge graph traversal and entity search
- **Code Analyst Agent**: Pattern detection and code analysis

Each agent communicates through a well-defined interface and coordinates through the Orchestrator to provide comprehensive analysis capabilities.

## Knowledge Graph Schema

Node types: Package, File, Class, Function
Relationships: CONTAINS, DEFINES, INHERITS_FROM, IMPORTS, CALLS, DECORATED_BY

The Neo4j database structures code repositories as connected entities enabling complex queries about dependencies, inheritance hierarchies, and code organization.

## Technical Stack

- Python 3.11
- FastAPI 0.104+
- Neo4j 5.14
- Docker and Docker Compose
- Pydantic v2 for validation
- WebSockets for real-time communication

## Installation

Prerequisites: Docker, Docker Compose, Git

Quick setup:

```bash
git clone <repository-url>
cd MultiAgentMCP
cp .env.example .env
# Edit .env with required variables
docker-compose up -d
curl http://localhost:8000/health
```

The system will be available at http://localhost:8000

## API Endpoints

### Health and Information

**GET /health**
Returns system health status for all components.

**GET /agents**
Lists all available agents and their capabilities.

### Chat Interfaces

**POST /api/chat**
Synchronous chat endpoint for single queries.

**WebSocket /ws/chat**
Real-time streaming chat for interactive conversations.

Message types include: session_created, thinking, analysis, response_chunk, response_complete

### Indexing Operations

**POST /api/index**
Start asynchronous repository indexing.

Request body:
```json
{"repo_url": "https://github.com/tiangolo/fastapi", "full_index": true}
```

Returns job_id for tracking progress.

**GET /api/index/jobs/{job_id}**
Get status of indexing job including progress metrics.

**GET /api/index/jobs**
List all indexing jobs with optional status filter.

**GET /api/index/status**
Get knowledge graph statistics and entity counts.

### Query Operations

**POST /api/query/find**
Find entities by name and type.

**POST /api/query/dependencies**
Get dependency chain for an entity.

**POST /api/query/dependents**
Get entities that depend on specified entity.

**POST /api/query/related**
Get related entities by relationship type.

**POST /api/query/execute**
Execute custom Cypher queries (advanced use).

### Analysis Operations

**POST /api/analysis/function**
Analyze function implementation and usage.

**POST /api/analysis/class**
Analyze class structure and inheritance.

**POST /api/analysis/patterns**
Detect design patterns in code.

**POST /api/analysis/compare**
Compare implementations across entities.

## Configuration

Environment variables control system configuration:

Required:
- NEO4J_USERNAME
- NEO4J_PASSWORD
- NEO4J_URI
- OPENAI_API_KEY

Optional:
- ENVIRONMENT (production/development/testing)
- LOG_LEVEL (DEBUG/INFO/WARNING/ERROR)
- GATEWAY_PORT (default: 8000)

See .env.example for complete configuration options.

## Project Structure

```
src/
├── agents/           # Agent implementations
├── gateway/          # FastAPI application
│   ├── main.py      # Application entry point
│   ├── models.py    # Pydantic models
│   ├── dependencies.py  # Dependency injection
│   └── routes/      # Route handlers
└── shared/          # Shared utilities
    ├── config.py
    ├── neo4j_service.py
    ├── ast_parser.py
    └── logger.py
```

## Development

Local development setup:

```bash
python3 -m venv venv
source venv/bin/activate
pip install -e ".[dev]"
pytest src/tests/ -v --cov=src
uvicorn src.gateway.main:app --reload --host 0.0.0.0 --port 8000
```

Code quality standards:

```bash
black src/              # Format code
ruff check src/         # Lint code
mypy src/ --ignore-missing-imports  # Type check
pytest src/tests/ -v --cov=src      # Run tests
```

## Production Deployment

The system is production-ready with Docker:

```bash
docker-compose up -d
docker-compose ps
docker-compose logs -f gateway
```

Monitor system health via /health endpoint.

For scaling: Gateway instances can be replicated behind a load balancer. Neo4j can be clustered for high availability.

## Performance Characteristics

Tested with FastAPI repository (1050 packages, 4360+ functions):

- Repository indexing: 5-10 minutes for 1000+ files
- Typical query response: 100-500ms
- WebSocket throughput: 50+ messages per second
- Connection pooling for efficient resource usage

## Security Considerations

Current implementation is suitable for development and internal use. Production deployments should implement:

- API key authentication
- Request rate limiting
- HTTPS/TLS encryption
- Database access controls
- API gateway with WAF

## Monitoring

The system provides:

- Structured JSON logging with correlation IDs
- Health check endpoints
- Performance metrics collection
- Error tracking and aggregation

Monitor key metrics:

- Request latency (p50, p95, p99)
- Job completion rates
- Neo4j query performance
- Agent response times
- Error rates by endpoint

## Known Limitations

1. Job tracking stored in-memory (cleared on restart)
2. Single Neo4j instance without clustering
3. No built-in API authentication
4. Synchronous repository indexing
5. Pattern detection limited to predefined patterns

## Future Enhancements

1. Persistent job queue with Redis/Celery
2. GraphQL API alongside REST
3. Vector embeddings for semantic search
4. Multi-repository dependency analysis
5. WebSocket-based collaborative analysis
6. Custom LLM provider support
7. Advanced caching strategies
8. Real-time analysis streaming

## Troubleshooting

Check container status:
```bash
docker-compose ps
docker-compose logs gateway
docker-compose logs neo4j
```

Verify Neo4j connectivity:
```bash
curl http://localhost:7474
docker exec multiagent-neo4j cypher-shell -u neo4j -p password "RETURN 1"
```

Common issues and solutions documented in docker-compose logs.

## Contributing

Contributions follow these guidelines:

- Code follows PEP 8 style
- All functions have type hints
- Docstrings use Google format
- Tests provided for new functionality
- Code passes quality checks

## License

This project is provided for educational and commercial use.

## Support

Documentation available at:
- API docs: http://localhost:8000/docs (Swagger UI)
- QUICK_START.md: Getting started guide
- ARCHITECTURE.md: Design decisions
- API.md: Complete endpoint reference

For issues, check logs and troubleshooting section above.

## Version

Version 1.0.0 - January 30, 2026

Initial release with complete multi-agent architecture, Neo4j indexing, REST and WebSocket APIs, and production Docker deployment.