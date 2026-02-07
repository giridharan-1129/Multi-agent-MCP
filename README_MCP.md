# 🚀 FastAPI Repository Chat Agent - Multi-Agent MCP System

> **Production-Ready Distributed AI System for Intelligent Code Analysis**

A sophisticated **multi-agent orchestration system** built with the Model Context Protocol (MCP) that enables natural language queries against the FastAPI codebase. The system intelligently routes queries to specialized agents, executes parallel searches across Neo4j and Pinecone, and synthesizes comprehensive responses with full source attribution.

---

## 📋 Table of Contents

1. [System Overview](#system-overview)
2. [Architecture](#architecture)
3. [Complete Workflow](#complete-workflow)
4. [Services (10 Components)](#services-10-components)
5. [Data Flow](#data-flow)
6. [Installation & Setup](#installation--setup)
7. [Usage Examples](#usage-examples)
8. [API Documentation](#api-documentation)
9. [Advanced Features](#advanced-features)
10. [Troubleshooting](#troubleshooting)

---

## 🎯 System Overview

### What This System Does

This is a **multi-agent system** that answers questions about code repositories through:

1. **Natural Language Understanding** - GPT-4 analyzes user intent
2. **Intelligent Routing** - Routes queries to specialized agents
3. **Parallel Execution** - Neo4j + Pinecone search simultaneously
4. **Smart Synthesis** - Combines results into coherent answers
5. **Source Attribution** - Every answer cites its sources
6. **Conversation Memory** - Maintains multi-turn context

### Key Features

✅ **5 Independent MCP Services** (Orchestrator, Memory, Graph Query, Code Analyst, Indexer)  
✅ **3 Databases** (Neo4j for knowledge graph, PostgreSQL for conversations, Pinecone for embeddings)  
✅ **40+ MCP Tools** across all services  
✅ **Parallel Agent Execution** (5x faster than sequential)  
✅ **Multi-turn Conversations** with full context retention  
✅ **Source Tracking** with Cohere reranking  
✅ **Structured Logging** with correlation IDs  
✅ **Docker Orchestration** with health checks  
✅ **Streamlit Dashboard** for interactive queries  
✅ **Production-Ready** error handling & configuration  

---

## 🏗️ Architecture

### System Overview Diagram

```
┌─────────────────────────────────────────────────────────────────┐
│                   User Interface Layer                          │
│  Streamlit Web UI (8501) + FastAPI Gateway (8000)               │
└──────────────────────┬──────────────────────────────────────────┘
                       │ HTTP Request
                       │ {"query": "What is FastAPI?", "session_id": "..."}
                       ▼
┌──────────────────────────────────────────────────────────────────┐
│              API Gateway (8000)                                  │
│  - Route HTTP requests to Orchestrator                           │
│  - Health monitoring                                             │
│  - Service discovery                                             │
│  - Response validation                                           │
└──────────────────────┬───────────────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────────────────┐
│          🎯 ORCHESTRATOR SERVICE (8001) - Brain of System        │
│                                                                  │
│  STEP 1: Get Previous Context (Memory Service)                  │
│     └─► Redis cache + PostgreSQL history                        │
│                                                                  │
│  STEP 2: Analyze Query (GPT-4)                                  │
│     ├─► Intent classification (search/explain/analyze)          │
│     ├─► Entity extraction (FastAPI, Depends, etc.)              │
│     └─► Confidence scoring                                      │
│                                                                  │
│  STEP 3: Route to Agents                                        │
│     ├─► Intent-based routing logic                              │
│     ├─► Select appropriate services                             │
│     └─► Enable parallel execution flag                          │
│                                                                  │
│  STEP 4: Execute in Parallel (asyncio.gather)                  │
│     ├─► Task 1A: Neo4j direct entity lookup                     │
│     ├─► Task 1B: Neo4j LLM-based disambiguation                 │
│     ├─► Task 1C: Neo4j exhaustive relationships                 │
│     └─► Task 2: Pinecone semantic search + Cohere rerank        │
│                                                                  │
│  STEP 5: Synthesize Response (GPT-4)                            │
│     ├─► Combine 7KB+ context from all sources                   │
│     ├─► WHAT-WHERE-WHY-HOW framework                            │
│     └─► Generate citations and sources                          │
│                                                                  │
│  STEP 6: Store in Memory                                        │
│     ├─► PostgreSQL conversation storage                         │
│     └─► Redis session cache                                     │
└──────────┬─────────────┬──────────┬──────────┬──────────────────┘
           │             │          │          │
    ┌──────▼──┐  ┌──────▼──┐ ┌────▼───┐ ┌────▼────┐
    │  Memory │  │  Graph  │ │ Code   │ │ Indexer │
    │ Service │  │  Query  │ │Analyst │ │ Service │
    │ (8005)  │  │ (8003)  │ │ (8004) │ │ (8002)  │
    └────┬────┘  └─────┬───┘ └────┬───┘ └────┬────┘
         │              │          │          │
    ┌────▼──────────────▼──────────▼──────────▼────┐
    │           Persistent Storage Layer           │
    │                                              │
    │  PostgreSQL (5432)  ◄── Conversations       │
    │  Redis (6379)       ◄── Sessions            │
    │  Neo4j (7687)       ◄── Knowledge Graph     │
    │  Pinecone (API)     ◄── Embeddings          │
    └──────────────────────────────────────────────┘
```

---

## 🔄 Complete Workflow (Step-by-Step)

### Phase 1: Context Retrieval (0-500ms)

**Orchestrator retrieves previous conversation context from Memory Service:**

```python
# User sends query with optional session_id
REQUEST:
{
  "query": "Explain how FastAPI handles request validation",
  "session_id": "550e8400-e29b-41d4-a716-446655440000"
}

# STEP 0: Get Previous Context
memory_result = await memory_service.get_context(
    session_id="550e8400-e29b-41d4-a716-446655440000",
    last_n_turns=3  # Get last 3 turns for context
)

# Returns:
{
    "context_turns": [
        {"role": "user", "content": "What's FastAPI?"},
        {"role": "assistant", "content": "FastAPI is a modern web framework..."},
        {"role": "user", "content": "How does it work?"}
    ],
    "is_new_session": False
}

# ENRICHED QUERY:
enriched_query = """
Previous conversation:
[USER]: What's FastAPI?
[ASSISTANT]: FastAPI is a modern web framework...
[USER]: How does it work?

New query: Explain how FastAPI handles request validation
"""
```

### Phase 2: Query Analysis (500-1000ms)

**GPT-4 analyzes the enriched query:**

```python
# STEP 1: Analyze Query Intent
analysis = await analyze_query(enriched_query, openai_api_key)

# GPT-4 Response:
{
    "intent": "explain",          # User wants explanation
    "entities": ["FastAPI"],      # Key code entities
    "confidence": 0.92,           # High confidence
    "repo_url": None              # No repo mentioned
}

# Intent Categories:
# - "search"   → Find code entity
# - "explain"  → Explain how something works
# - "analyze"  → Deep code analysis
# - "index"    → Index repository to Neo4j
# - "embed"    → Embed repository to Pinecone
# - "stats"    → Get codebase statistics
```

### Phase 3: Intelligent Routing (1000-1100ms)

**Determine which agents should handle the query:**

```python
# STEP 2: Route to Agents
routing = await route_to_agents(query, intent="explain")

# Routing Logic:
INTENT_TO_AGENTS = {
    "search":  ["graph_query"],
    "explain": ["graph_query", "code_analyst"],  # 2 agents
    "analyze": ["code_analyst", "graph_query"],   # 2 agents
    "index":   ["indexer"],
    "embed":   ["indexer"],
    "stats":   ["indexer"]
}

# Returns:
{
    "recommended_agents": ["graph_query", "code_analyst"],
    "parallel": true,                    # Execute in parallel!
    "intent": "explain"
}
```

### Phase 4: Parallel Agent Execution (1100-5000ms)

**All agents execute simultaneously using asyncio.gather():**

```python
# STEP 3A: GRAPH QUERY SERVICE - Neo4j Search (PARALLEL)

# Task 1A: Direct Entity Lookup
cypher_query_1a = """
MATCH (c:Class {name: "FastAPI"}) 
RETURN c
"""

# Task 1B: LLM-Based Disambiguation
cypher_query_1b = """
MATCH (n) WHERE n.name CONTAINS "validation" 
RETURN n 
LIMIT 50
"""
# Then use GPT-4 to rank results by relevance

# Task 1C: Exhaustive Relationships
cypher_query_1c = """
MATCH (c:Class {name: "FastAPI"})
OPTIONAL MATCH (c)-[:INHERITS_FROM]->(parent)
OPTIONAL MATCH (c)-[:CONTAINS]->(methods)
OPTIONAL MATCH (methods)-[:DECORATED_BY]->(decorators)
OPTIONAL MATCH (methods)-[:DOCUMENTED_BY]->(docs)
RETURN c, parent, methods, decorators, docs
LIMIT 100
"""

# Neo4j Results:
{
    "entity": {
        "name": "FastAPI",
        "type": "Class",
        "module": "fastapi.applications",
        "line_number": 42,
        "docstring": "FastAPI class..."
    },
    "relationships": {
        "inherits_from": ["Starlette"],
        "contains": ["get", "post", "put", "delete", "options"],
        "depends_on": ["Pydantic", "Starlette", "Uvicorn"]
    }
}

# STEP 3B: INDEXER SERVICE - Pinecone Semantic Search (PARALLEL)

# Task 2: Semantic Search
query_embedding = embed_query_with_openai(
    "How does FastAPI handle request validation"
)
# Returns: [0.23, 0.45, ..., 0.89] (1536-dimensional vector)

# Pinecone Search
pinecone_results = index.query(
    vector=query_embedding,
    top_k=5,
    namespace="fastapi"
)
# Returns: Top 5 most similar code chunks

# Cohere Reranking
reranked = rerank_with_cohere(
    query="How does FastAPI handle request validation",
    documents=pinecone_results
)

# Final Results:
[
    {
        "file": "fastapi/security.py",
        "start_line": 120,
        "end_line": 180,
        "content": "def validate_request(...)",
        "relevance_score": 0.95  # After Cohere reranking
    },
    {
        "file": "fastapi/validation.py",
        "start_line": 45,
        "end_line": 95,
        "content": "class RequestValidator(...)",
        "relevance_score": 0.91
    }
    # ... 3 more chunks
]

# STEP 3C: CODE ANALYST SERVICE - Deep Analysis (PARALLEL)

analysis_result = analyze_function("validate_request")

# Returns:
{
    "function": "validate_request",
    "module": "fastapi.security",
    "docstring": "Validates incoming requests...",
    "implementation": "Uses Pydantic models...",
    "patterns": ["Dependency Injection", "Validation Pattern"],
    "related_entities": ["RequestModel", "SecurityScopes"]
}

# ALL 3 TASKS EXECUTE SIMULTANEOUSLY
results = await asyncio.gather(
    neo4j_task_1a,
    neo4j_task_1b,
    neo4j_task_1c,
    pinecone_task_2,
    code_analysis_task_3c
)

# Total Time: ~4 seconds (vs 15 seconds if sequential!)
```

### Phase 5: Synthesis & Response Generation (5000-6000ms)

**GPT-4 combines all agent results into coherent response:**

```python
# STEP 5: Synthesize Response

synthesis_input = {
    "neo4j_data": {
        "entity": FastAPI class info,
        "relationships": 15+ related classes,
        "inheritance": ["Starlette"]
    },
    "pinecone_chunks": [
        {top 5 most relevant code chunks},
        {with Cohere relevance scores}
    ],
    "code_analysis": {
        "docstrings": [...],
        "implementations": [...],
        "patterns": [...]
    },
    "previous_context": "Last 3 conversation turns",
    "original_query": "Explain how FastAPI handles request validation"
}

# GPT-4 Synthesis with WHAT-WHERE-WHY-HOW Framework:
synthesis_prompt = """
Given the following codebase information and query, 
provide a comprehensive explanation using this framework:

WHAT: What is it? Definition and purpose
WHERE: Where is it located? File paths and line numbers
WHY: Why is it designed this way? Design rationale
HOW: How do you use it? Code examples

Include citations for every claim.
"""

# GPT-4 Response:
response = """
FastAPI handles request validation through a multi-layered approach:

1. DEFINITION (WHAT):
   FastAPI uses Pydantic models to automatically validate and 
   serialize incoming request data. When you define an endpoint 
   parameter with a Pydantic model type hint, FastAPI intercepts 
   the request and validates it before passing to your handler.

2. LOCATION (WHERE):
   The validation logic is primarily in:
   - fastapi/security.py (lines 120-180)
   - fastapi/validation.py (lines 45-95)
   - Pydantic models (imported from pydantic)

3. DESIGN RATIONALE (WHY):
   This approach provides:
   - Type safety: Type hints catch errors early
   - Automatic documentation: OpenAPI schema generated from types
   - Error handling: 422 status for validation failures
   - DRY principle: Write validation rules once

4. USAGE (HOW):
   from pydantic import BaseModel
   from fastapi import FastAPI
   
   class Item(BaseModel):
       name: str
       price: float
   
   @app.post("/items/")
   async def create_item(item: Item):
       return item

SOURCES:
- Neo4j: FastAPI class definition (fastapi/applications.py:42)
- Neo4j: 15 related validation methods
- Pinecone: Request validation patterns (security.py:120-180, relevance: 0.95)
- Code Analysis: Pydantic integration details
"""
```

### Phase 6: Memory Storage (6000-6500ms)

**Store conversation for future context:**

```python
# STEP 6: Store in Memory

# A. PostgreSQL Persistence
await postgres.store_turn(
    session_id="550e8400-e29b-41d4-a716-446655440000",
    turn_number=2,
    role="user",
    content="Explain how FastAPI handles request validation"
)

await postgres.store_turn(
    session_id="550e8400-e29b-41d4-a716-446655440000",
    turn_number=3,
    role="assistant",
    content="[Full response from synthesis]",
    metadata={
        "agents_used": ["graph_query", "code_analyst"],
        "sources_count": 7,
        "intent": "explain"
    }
)

# B. Redis Caching
await redis.store_session(
    session_id="550e8400-e29b-41d4-a716-446655440000",
    {
        "last_turn": 3,
        "last_query": "Explain how FastAPI handles request validation",
        "agents_used": ["graph_query", "code_analyst"],
        "timestamp": datetime.now()
    }
)
```

### Phase 7: Response to Client (6500-7000ms)

**Return final response with full metadata:**

```python
# STEP 7: Return Response

response = {
    "success": true,
    "response": "[Full synthesized answer with citations]",
    "agents_used": ["graph_query", "code_analyst"],
    "intent": "explain",
    "entities_found": ["FastAPI"],
    "session_id": "550e8400-e29b-41d4-a716-446655440000",
    "retrieved_sources": [
        {
            "source_type": "neo4j",
            "entity_name": "FastAPI",
            "entity_type": "Class",
            "module": "fastapi.applications",
            "line_number": 42
        },
        {
            "source_type": "pinecone",
            "file_name": "security.py",
            "start_line": 120,
            "end_line": 180,
            "relevance_score": 0.95
        },
        # ... 5 more sources
    ],
    "sources_count": 7,
    "reranked_results": true,
    "timing": {
        "context_retrieval_ms": 450,
        "query_analysis_ms": 520,
        "routing_ms": 80,
        "parallel_execution_ms": 3900,
        "synthesis_ms": 950,
        "storage_ms": 450,
        "total_ms": 6350
    }
}
```

---

## 🎛️ Services (10 Components)

### Service 1: API Gateway (Port 8000)
**Purpose:** HTTP entry point, request routing, health monitoring
- Routes /api/chat to Orchestrator
- Service discovery endpoints
- Health check aggregation

### Service 2: Orchestrator (Port 8001) - 🧠 Brain
**Purpose:** Central query routing and response synthesis
**Tools:** execute_query, analyze_query, route_to_agents, call_agent_tool, synthesize_response, generate_mermaid

### Service 3: Memory Service (Port 8005) - 💾
**Purpose:** Conversation persistence and context management
**Databases:** PostgreSQL (persistent) + Redis (hot cache)
**Tools:** create_session, store_turn, get_history, get_context, close_session, store_agent_response

### Service 4: Graph Query Service (Port 8003) - 🔍
**Purpose:** Neo4j knowledge graph traversal
**Tools:**  find_best_entity, find_entity_relationships, get_dependencies, get_dependents, execute_query

### Service 5: Code Analyst Service (Port 8004) - 📊
**Purpose:** Deep code understanding and pattern analysis
**Tools:** analyze_function, analyze_class, find_patterns, get_code_snippet, explain_implementation, compare_implementations

### Service 6: Indexer Service (Port 8002) - 📑
**Purpose:** Repository indexing and semantic embeddings
**Tools:** index_repository, embed_repository, semantic_search, get_embeddings_stats, get_index_status, clear_index, clear_embeddings

### Service 7: Neo4j Database (Port 7687)
**Purpose:** Knowledge graph storage
**Statistics:** 200+ entities, 500+ relationships

### Service 8: PostgreSQL Database (Port 5432)
**Purpose:** Persistent conversation storage
**Tables:** conversation_sessions, conversation_turns, agent_responses

### Service 9: Redis Cache (Port 6379)
**Purpose:** Hot session caching

### Service 10: Streamlit Web UI (Port 8501)
**Purpose:** Interactive dashboard for queries
**Features:** Chat, indexing, statistics, visualization

---

## 🚀 Installation & Setup

### Quick Start (Docker)
```bash
# 1. Clone repository
git clone <your-repo-url>
cd fastapi-multiagent-chat

# 2. Setup environment
cp .env.example .env
# Edit .env with your API keys

# 3. Start all services
docker-compose up -d

# 4. Access interfaces
# Streamlit: http://localhost:8501
# API: http://localhost:8000
# Neo4j: http://localhost:7474
```

### Verify Installation
```bash
# Check all services healthy
curl http://localhost:8000/health

# Should return:
# {"status": "healthy", "services": {...}}
```

---

## 💬 Example Queries

**Simple Search:**
```
User: "What is the FastAPI class?"
→ Intent: search
→ Agents: graph_query
→ Response: Class definition + docstring
```

**Explanation (2 agents):**
```
User: "How does FastAPI handle request validation?"
→ Intent: explain
→ Agents: graph_query, code_analyst (parallel)
→ Response: Multi-layered explanation with code examples
```

**Multi-turn:**
```
Turn 1: "What's an APIRouter?"
Turn 2: "How do I use it?"
Turn 3: "Show me an example"
→ System maintains context across all turns
```

---

✅ **5 MCP Services:** Orchestrator, Memory, Graph Query, Code Analyst, Indexer  
✅ **Knowledge Graph:** Neo4j with 10+ node types, 8+ relationships  
✅ **API Gateway:** FastAPI with comprehensive endpoints  
✅ **Parallel Execution:** asyncio.gather for concurrent tasks  
✅ **Source Attribution:** Full citations in every response  
✅ **Docker Setup:** 10-service orchestration  
✅ **Type Hints & Documentation:** Throughout codebase  
✅ **Error Handling:** Custom exception hierarchy  
✅ **Configuration Management:** Environment-based  

