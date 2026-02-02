# System Architecture

Comprehensive overview of the multi-agent system architecture.

## 🏗️ High-Level Architecture
```
┌─────────────────────────────────────────────────────────────┐
│                    User/Client Layer                        │
│                   (REST API Requests)                       │
└────────────┬──────────────────────────────────────────────┘
             │
             ▼
┌─────────────────────────────────────────────────────────────┐
│                   FastAPI Gateway                           │
│                    (Port 8000)                              │
│  - HTTP Request Handling                                    │
│  - Request Routing                                          │
│  - Response Serialization                                   │
│  - Error Handling                                           │
│  - CORS & Security                                          │
└────────┬────────────────────────────┬──────────────────────┘
         │                            │
         ▼                            ▼
┌──────────────────────┐  ┌──────────────────────┐
│ Orchestrator Agent   │  │ Query Router         │
│  (Port 8001)         │  │                      │
│                      │  │ - Analyze query      │
│ - Coordinate agents  │  │ - Route to agents    │
│ - Manage sessions    │  │ - Combine results    │
│ - Synthesize answers │  └──────────────────────┘
└──────────┬───────────┘
           │
    ┌──────┴──────┬──────────┬──────────┐
    ▼             ▼          ▼          ▼
┌────────┐  ┌────────┐ ┌────────┐ ┌────────┐
│Indexer │  │ Graph  │ │ Code   │ │ Other  │
│Agent   │  │ Query  │ │Analyst │ │ Agents │
│(8002)  │  │Agent   │ │(8004)  │ │        │
│        │  │(8003)  │ │        │ │        │
├────────┤  ├────────┤ ├────────┤ ├────────┤
│- Index │  │- Find  │ │-Analyze│ │        │
│- Parse │  │- Query │ │-Detect │ │        │
│- Store │  │- Search│ │-Compare│ │        │
└───┬────┘  └───┬────┘ └───┬────┘ └────────┘
    │          │          │
    └──────────┼──────────┘
               ▼
    ┌──────────────────────┐
    │   Neo4j Database     │
    │ Knowledge Graph      │
    │   (Port 7687)        │
    │                      │
    │ - Nodes (Classes,    │
    │   Functions, Modules)│
    │ - Relationships      │
    │   (INHERITS, IMPORTS)│
    └──────────────────────┘
```

## 🧩 Component Details

### 1. FastAPI Gateway

**Purpose**: Main entry point, HTTP request handling

**Responsibilities**:
- Accept HTTP requests
- Route to appropriate agents
- Manage session context
- Return formatted responses
- Handle errors and logging

**Key Files**: `src/gateway/main.py`

**Endpoints**:
```
POST /api/chat              - Chat interaction
POST /api/index             - Index repository
GET  /api/index/status      - Get indexing status
POST /api/query/find        - Find entity
POST /api/query/dependencies- Get dependencies
POST /api/analysis/*        - Analyze code
GET  /health                - Health check
GET  /agents                - List agents
```

### 2. Orchestrator Agent

**Purpose**: Central coordinator for multi-agent orchestration

**Responsibilities**:
- Analyze user queries
- Determine required agents
- Route queries to agents
- Manage conversation sessions
- Synthesize responses from multiple agents

**Key Files**: `src/agents/orchestrator_agent.py`

**Tools**:
- `analyze_query`: Classify intent, extract entities
- `create_conversation`: Start new session
- `get_conversation_context`: Retrieve history
- `add_conversation_message`: Store message
- `synthesize_response`: Combine agent outputs

**Key Concepts**:
- Query intent detection (explanation, search, analysis, etc.)
- Entity extraction (class names, function names, etc.)
- Agent routing logic
- Conversation memory management

### 3. Indexer Agent

**Purpose**: Index repositories into knowledge graph

**Responsibilities**:
- Download repositories
- Parse Python files
- Extract code structure
- Build relationships
- Populate Neo4j

**Key Files**: `src/agents/indexer_agent.py`

**Tools**:
- `index_repository`: Full repository indexing
- `get_index_status`: Graph statistics
- `clear_index`: Reset knowledge graph

**Process**:
1. Download repo from GitHub
2. Find all Python files
3. Parse each file with AST
4. Extract entities (classes, functions)
5. Build relationships (imports, inheritance, calls)
6. Create nodes in Neo4j
7. Create relationships in Neo4j

### 4. Graph Query Agent

**Purpose**: Query knowledge graph for information

**Responsibilities**:
- Search for entities
- Find relationships
- Trace dependencies
- Execute Cypher queries

**Key Files**: `src/agents/graph_query_agent.py`

**Tools**:
- `find_entity`: Search for class/function/module
- `get_dependencies`: What does entity depend on
- `get_dependents`: What depends on entity
- `execute_query`: Custom Cypher queries
- `search_entities`: Pattern-based search
- `get_relationships`: Find connections

**Query Types**:
- Simple entity lookup
- Dependency analysis
- Relationship traversal
- Pattern matching

### 5. Code Analyst Agent

**Purpose**: Analyze code patterns and provide insights

**Responsibilities**:
- Analyze functions/classes
- Detect design patterns
- Compare implementations
- Identify best practices

**Key Files**: `src/agents/code_analyst_agent.py`

**Tools**:
- `analyze_function`: Deep function analysis
- `analyze_class`: Class structure analysis
- `find_patterns`: Detect design patterns
- `compare_implementations`: Compare two entities

**Patterns Detected**:
- Singleton patterns
- Decorator patterns
- Inheritance hierarchies
- Method patterns

## 🗄️ Data Model

### Neo4j Schema
```
Nodes:
├── Module
│   ├── name
│   ├── file_path
│   └── content
├── Class
│   ├── name
│   ├── module
│   ├── docstring
│   ├── line_number
│   └── bases
├── Function
│   ├── name
│   ├── module
│   ├── docstring
│   ├── line_number
│   ├── is_async
│   ├── parameters
│   └── returns

Relationships:
├── INHERITS_FROM (Class -> Class)
├── IMPORTS (Entity -> Module)
├── CALLS (Function -> Function)
├── DECORATED_BY (Entity -> Decorator)
├── HAS_PARAMETER (Function -> Parameter)
├── CONTAINS (Module -> Entity)
└── DEPENDS_ON (Entity -> Entity)
```

## 🔄 Request Flow Example

### Example: "How does FastAPI handle dependency injection?"
```
1. User sends query to /api/chat
   ↓
2. Gateway receives request, creates correlation ID
   ↓
3. Orchestrator analyzes query
   - Intent: "explanation"
   - Entities: ["dependency", "injection", "FastAPI"]
   - Required agents: [graph_query, code_analyst]
   ↓
4. Route to agents:
   - Graph Query Agent: Find "Depends" class/function
   - Code Analyst Agent: Analyze "Depends" implementation
   ↓
5. Agents query Neo4j:
   - Find Depends entity
   - Get its relationships
   - Analyze its structure
   ↓
6. Orchestrator synthesizes results:
   - Combine findings from both agents
   - Format coherent response
   ↓
7. Gateway returns response to user
   - Include session_id
   - Include agents used
   - Include correlation_id for tracing
```

## 🔐 Security & Error Handling

### Error Handling Hierarchy
```
MCPException (base)
├── AgentError
│   ├── AgentTimeoutError
│   ├── AgentConnectionError
│   └── AgentExecutionError
├── DatabaseError
│   ├── Neo4jError
│   └── Neo4jConnectionError
├── RepositoryError
│   ├── RepositoryCloneError
│   ├── RepositoryIndexingError
│   └── FileParsingError
├── CodeAnalysisError
│   ├── EntityNotFoundError
│   └── PatternAnalysisError
└── LLMError
    ├── LLMRateLimitError
    ├── LLMAuthenticationError
    └── LLMGenerationError
```

### Correlation ID Tracing

Every request gets a unique correlation ID that:
- Flows through all agents
- Appears in all logs
- Returned in response
- Enables request tracing
```
Request → Gateway → Orchestrator → Agents → Neo4j → Response
  ↑          ↑           ↑           ↑       ↑        ↑
  └──────────correlation_id tracking───────────────────┘
```

## 🔌 MCP Protocol

All agents communicate via Model Context Protocol:
```
MCPMessage
├── message_id: str
├── sender: str
├── recipient: str
├── tool_name: str
├── parameters: Dict
├── correlation_id: str
└── timestamp: str

MCPResponse
├── message_id: str
├── sender: str
├── result: ToolResult
├── execution_time_ms: float
└── correlation_id: str
```

## 📊 Conversation Management

Sessions store:
- Conversation ID
- Message history
- User info
- Context data
- Last updated timestamp

Memory management:
- Keep last 50 messages in memory
- Older messages stay in database
- Configurable limits
- Automatic cleanup

## 🎯 Design Principles

1. **Separation of Concerns**: Each agent has specific responsibility
2. **Scalability**: Agents can run independently
3. **Fault Tolerance**: Graceful error handling at each layer
4. **Observability**: Comprehensive logging with correlation IDs
5. **Type Safety**: Full type hints throughout
6. **Async/Await**: Non-blocking operations where possible
7. **Configuration Management**: Environment-based config
8. **Clean Code**: SOLID principles, DRY, clear documentation

## 🚀 Performance Considerations

### Caching Opportunities
- Repository data (after indexing)
- Query results (frequently accessed entities)
- API responses (for identical queries)

### Optimization Strategies
- Parallel agent execution
- Query result pagination
- Connection pooling
- Index optimization in Neo4j
- Lazy loading of large datasets

### Monitoring Points
- Agent response times
- Query execution times
- Neo4j query performance
- Memory usage
- Error rates

---

For implementation details, see specific agent documentation.
