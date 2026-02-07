import streamlit as st
import requests
import time
import os
import sys
import logging

sys.path.insert(0, '/mnt/project')

from mermaid_renderer import render_mermaid_diagram
from relationship_mappings import get_cypher_query_templates, get_query_description

# Setup logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

GATEWAY_URL = os.getenv("GATEWAY_URL", "http://gateway:8000")
INDEXER_SERVICE = os.getenv("INDEXER_SERVICE_URL", "http://indexer_service:8002")
ORCHESTRATOR_SERVICE = os.getenv("ORCHESTRATOR_SERVICE_URL", "http://orchestrator_service:8001")

# Page config
st.set_page_config(
    page_title="Agentic Codebase Chat",
    page_icon="",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
<style>
    .citation-box {
        background-color: #e7f3ff;
        border-left: 4px solid #2196F3;
        padding: 12px;
        margin: 8px 0;
        border-radius: 4px;
        font-size: 0.9rem;
        color: #1a1a1a;
    }
    .citation-box strong {
        color: #0d47a1;
        font-weight: 700;
    }
    .citation-box code {
        background-color: #d6ebf5;
        color: #0d47a1;
        padding: 2px 4px;
        border-radius: 2px;
    }
    .agent-badge {
        background-color: #d4edda;
        border: 1px solid #c3e6cb;
        border-radius: 20px;
        padding: 6px 12px;
        display: inline-block;
        margin: 4px 4px;
        font-weight: bold;
        font-size: 0.85rem;
        color: #155724;
    }
</style>
""", unsafe_allow_html=True)

# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

if "indexing_embedding_active" not in st.session_state:
    st.session_state.indexing_embedding_active = False
if "current_operation" not in st.session_state:
    st.session_state.current_operation = None  # "indexing" or "embedding"
if "operation_progress" not in st.session_state:
    st.session_state.operation_progress = 0
if "operation_message" not in st.session_state:
    st.session_state.operation_message = ""
if "last_repo_url" not in st.session_state:
    st.session_state.last_repo_url = None
if "agentic_history" not in st.session_state:
    st.session_state.agentic_history = {}
if "messages" not in st.session_state:
    st.session_state.messages = []
if "session_id" not in st.session_state:
    st.session_state.session_id = None
if "neo4j_stats" not in st.session_state:
    st.session_state.neo4j_stats = None
if "neo4j_stats_timestamp" not in st.session_state:
    st.session_state.neo4j_stats_timestamp = None
if "pinecone_stats" not in st.session_state:
    st.session_state.pinecone_stats = None
if "pinecone_stats_timestamp" not in st.session_state:
    st.session_state.pinecone_stats_timestamp = None
# ============================================================================
# HELPER FUNCTIONS FOR FETCHING REPO LISTS
# ============================================================================

def get_indexed_repos():
    """
    Query Neo4j directly to get list of indexed repositories.
    Returns list of dicts: [{"name": "fastapi", "url": "...", "nodes": 1250, "indexed_date": "2026-02-06"}]
    """
    try:
        from neo4j import GraphDatabase
        
        # Connect directly to Neo4j (bypass orchestrator)
        NEO4J_URI = os.getenv("NEO4J_URI", "bolt://neo4j:7687")
        NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
        NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password")
        
        driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
        
        with driver.session() as session:
            cypher = """
            MATCH (f:File)
            WHERE f.repo_url IS NOT NULL
            WITH f.repo_url as repo_url, COUNT(f) as file_count
            MATCH (n) WHERE n.repo_url = repo_url
            RETURN DISTINCT repo_url, COUNT(n) as node_count
            ORDER BY repo_url
            """
            
            result = session.run(cypher)
            repos = []
            
            for record in result:
                repo_url = record.get("repo_url", "")
                node_count = record.get("node_count", 0)
                
                if repo_url:
                    repo_name = repo_url.split("/")[-1].replace(".git", "")
                    repos.append({
                        "name": repo_name,
                        "url": repo_url,
                        "nodes": node_count,
                        "indexed_date": "N/A"
                    })
            
            driver.close()
            return repos
            
    except Exception as e:
        logger.error(f"Error fetching indexed repos: {e}")
        # Fallback: return empty list (don't timeout)
        return []


def get_embedded_repos():
    """
    Query Pinecone directly to get list of embedded repositories with metadata.
    Returns list of dicts: [{"name": "fastapi", "chunks": 245, "embedded_date": "2026-02-06"}]
    """
    try:
        import pinecone
        
        # Connect directly to Pinecone (bypass orchestrator)
        PINECONE_API_KEY = os.getenv("PINECONE_API_KEY", "")
        PINECONE_INDEX = os.getenv("PINECONE_INDEX", "code-search")
        
        if not PINECONE_API_KEY:
            logger.warning("PINECONE_API_KEY not set - skipping embedded repos")
            return []
        
        # Initialize Pinecone
        pc = pinecone.Pinecone(api_key=PINECONE_API_KEY)
        index = pc.Index(PINECONE_INDEX)
        
        # Get index stats
        index_stats = index.describe_index_stats()
        
        # Extract namespaces (repos) from index stats
        repos = []
        namespaces = index_stats.get("namespaces", {})
        
        for namespace_name, namespace_info in namespaces.items():
            # Skip empty namespaces
            if not namespace_name:
                continue
            
            vector_count = namespace_info.get("vector_count", 0)
            
            if vector_count > 0:
                # Extract repo name from namespace (e.g., "fastapi" from "fastapi_chunks")
                repo_name = namespace_name.replace("_chunks", "").replace("_vectors", "")
                
                repos.append({
                    "name": repo_name,
                    "chunks": vector_count,
                    "embedded_date": "N/A"
                })
        
        # If no namespaces found, try to get total vector count
        if not repos and index_stats.get("total_vector_count", 0) > 0:
            total_vectors = index_stats.get("total_vector_count", 0)
            repos.append({
                "name": "Embedded Repos",
                "chunks": total_vectors,
                "embedded_date": "N/A"
            })
        
        return repos
        
    except Exception as e:
        logger.error(f"Error fetching embedded repos: {e}")
        # Fallback: return empty list (don't timeout)
        return []
# ============================================================================
# TABS
# ============================================================================
tab_chat, tab_tools = st.tabs(["Chat", "Tools"])

# ============================================================================
# TAB 1: CHAT
# ============================================================================
with tab_chat:
    # SIDEBAR - Repository Status & Stats
    with st.sidebar:
        st.header("📚 Repository Status")
        
        st.divider()
        
        # Only fetch stats if they haven't been fetched in this session
        # This prevents unnecessary calls on page reload
        STATS_CACHE_TTL = 300  # 5 minutes cache
        current_time = time.time()
        
        # ====================================================================
        # NEO4J STATS
        # ====================================================================
        st.subheader("📊 Neo4j Index")
        
        col_stats, col_refresh = st.columns([3, 1])
        with col_refresh:
            if st.button("🔄", key="refresh_neo4j_btn", help="Refresh Neo4j stats"):
                st.session_state.neo4j_stats = None
                st.session_state.neo4j_stats_timestamp = None
        
        if st.session_state.neo4j_stats is None or (st.session_state.neo4j_stats_timestamp and current_time - st.session_state.neo4j_stats_timestamp > STATS_CACHE_TTL):
            try:
                from neo4j import GraphDatabase
                
                NEO4J_URI = os.getenv("NEO4J_URI", "bolt://neo4j:7687")
                NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
                NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password")
                
                driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
                
                with driver.session() as session:
                    # Count all node types that exist in database
                    # Nodes: Module, Class, Function, Method, Parameter, Decorator, Import, Docstring
                    classes = session.run("MATCH (c:Class) RETURN COUNT(c) as count").single()[0]
                    functions = session.run("MATCH (f:Function) RETURN COUNT(f) as count").single()[0]
                    methods = session.run("MATCH (m:Method) RETURN COUNT(m) as count").single()[0]
                    modules = session.run("MATCH (m:Module) RETURN COUNT(m) as count").single()[0]
                    parameters = session.run("MATCH (p:Parameter) RETURN COUNT(p) as count").single()[0]
                    decorators = session.run("MATCH (d:Decorator) RETURN COUNT(d) as count").single()[0]
                    imports = session.run("MATCH (i:Import) RETURN COUNT(i) as count").single()[0]
                    docstrings = session.run("MATCH (d:Docstring) RETURN COUNT(d) as count").single()[0]
                    files = session.run("MATCH (f:File) RETURN COUNT(f) as count").single()[0]

                    
                    # Total nodes
                    total = session.run("MATCH (n) RETURN COUNT(n) as count").single()[0]
                
                driver.close()
                
                st.session_state.neo4j_stats = {
                    "classes": classes,
                    "functions": functions + methods,  # Combine functions and methods
                    "modules": modules,
                    "parameters": parameters,
                    "decorators": decorators,
                    "imports": imports,
                    "docstrings": docstrings,
                    "files": files,
                    "total_nodes": total
                }
                import time
                st.session_state.neo4j_stats_timestamp = time.time()
                
            except Exception as e:
                st.session_state.neo4j_stats = {"error": str(e)[:50]}
        
        # Display cached stats
        if st.session_state.neo4j_stats and "error" not in st.session_state.neo4j_stats:
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Classes", st.session_state.neo4j_stats.get("classes", 0))
            with col2:
                st.metric("Functions", st.session_state.neo4j_stats.get("functions", 0))
            with col3:
                st.metric("Modules", st.session_state.neo4j_stats.get("modules", 0))
            
            # Additional node types in expandable section
            with st.expander("📊 More node types"):
                col4, col5, col6 = st.columns(3)
                with col4:
                    st.metric("Parameters", st.session_state.neo4j_stats.get("parameters", 0))
                with col5:
                    st.metric("Decorators", st.session_state.neo4j_stats.get("decorators", 0))
                with col6:
                    st.metric("Imports", st.session_state.neo4j_stats.get("imports", 0))
                
                st.metric("Docstrings", st.session_state.neo4j_stats.get("docstrings", 0))
            
            st.caption(f"Total: {st.session_state.neo4j_stats.get('total_nodes', 0)} nodes")
        else:
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Classes", "N/A")
            with col2:
                st.metric("Functions", "N/A")
            with col3:
                st.metric("Modules", "N/A")
            if st.session_state.neo4j_stats and "error" in st.session_state.neo4j_stats:
                st.caption(f"Error: {st.session_state.neo4j_stats['error']}")
        
        st.divider()
        
        # ====================================================================
        # PINECONE STATS
        # ====================================================================
        st.subheader("⚡ Pinecone Embeddings")
        
        col_stats, col_refresh = st.columns([3, 1])
        with col_refresh:
            if st.button("🔄", key="refresh_pinecone_btn", help="Refresh Pinecone stats"):
                st.session_state.pinecone_stats = None
                st.session_state.pinecone_stats_timestamp = None
        
        # Fetch stats if not cached - Query Pinecone directly
        if st.session_state.pinecone_stats is None or (st.session_state.pinecone_stats_timestamp and current_time - st.session_state.pinecone_stats_timestamp > STATS_CACHE_TTL):
            try:
                import pinecone
                
                PINECONE_API_KEY = os.getenv("PINECONE_API_KEY", "")
                PINECONE_INDEX = os.getenv("PINECONE_INDEX", "code-search")
                
                if not PINECONE_API_KEY:
                    st.session_state.pinecone_stats = {"error": "API key not set"}
                else:
                    pc = pinecone.Pinecone(api_key=PINECONE_API_KEY)
                    index = pc.Index(PINECONE_INDEX)
                    
                    stats = index.describe_index_stats()
                    
                    st.session_state.pinecone_stats = {
                        "vectors_stored": stats.get("total_vector_count", 0),
                        "dimension": 1536,
                        "index_name": PINECONE_INDEX
                    }
                    import time
                    st.session_state.pinecone_stats_timestamp = time.time()
                    
            except Exception as e:
                st.session_state.pinecone_stats = {"error": str(e)[:50]}
        
        # Display cached stats
        if st.session_state.pinecone_stats and "error" not in st.session_state.pinecone_stats:
            st.metric("Vectors Stored", st.session_state.pinecone_stats.get("vectors_stored", 0))
            st.metric("Dimension", st.session_state.pinecone_stats.get("dimension", 1536))
            st.caption(f"Index: {st.session_state.pinecone_stats.get('index_name', 'code-search')}")
        else:
            st.metric("Vectors Stored", "N/A")
            st.metric("Dimension", "1536")
            st.caption("Index: code-search")
            if st.session_state.pinecone_stats and "error" in st.session_state.pinecone_stats:
                st.caption(f"Status: {st.session_state.pinecone_stats['error']}")
        
        
        st.divider()
        
        # ====================================================================
        # ALL NODE TYPES & RELATIONSHIPS (EXPANDABLE)
        # ====================================================================
        st.subheader("🔗 Knowledge Graph Details")
        
        def get_all_relationships():
            """Query Neo4j to get all relationship types and their counts."""
            try:
                from neo4j import GraphDatabase
                
                NEO4J_URI = os.getenv("NEO4J_URI", "bolt://neo4j:7687")
                NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
                NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "password")
                
                driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
                
                with driver.session() as session:
                    # Get all relationship types and counts
                    cypher = """
                    MATCH ()-[r]->()
                    WITH type(r) as rel_type
                    RETURN rel_type, COUNT(*) as count
                    ORDER BY count DESC
                    """
                    
                    result = session.run(cypher)
                    relationships = []
                    
                    for record in result:
                        rel_type = record.get("rel_type", "")
                        count = record.get("count", 0)
                        
                        if rel_type:
                            relationships.append({
                                "type": rel_type,
                                "count": count
                            })
                
                driver.close()
                return relationships
                
            except Exception as e:
                logger.error(f"Error fetching relationships: {e}")
                return []
        
        # ====================================================================
        # ALL NODE TYPES (Comprehensive list)
        # ====================================================================
        with st.expander("📊 All Node Types (9 types)", expanded=False):
            if st.session_state.neo4j_stats and "error" not in st.session_state.neo4j_stats:
                node_stats = st.session_state.neo4j_stats
                
                # Define all possible node types in order
                all_node_types = [
                        {"label": "📦 Module", "key": "modules", "icon": "📦"},
                        {"label": "🏛️ Class", "key": "classes", "icon": "🏛️"},
                        {"label": "⚙️ Function/Method", "key": "functions", "icon": "⚙️"},
                        {"label": "📍 Parameter", "key": "parameters", "icon": "📍"},
                        {"label": "✨ Decorator", "key": "decorators", "icon": "✨"},
                        {"label": "📥 Import", "key": "imports", "icon": "📥"},
                        {"label": "📝 Docstring", "key": "docstrings", "icon": "📝"},
                        {"label": "📄 File", "key": "files", "icon": "📄"},
                    ]
                
                # Create 3 columns for better layout
                cols = st.columns(3)
                
                for idx, node_type in enumerate(all_node_types):
                    col = cols[idx % 3]
                    count = node_stats.get(node_type["key"], 0)
                    
                    with col:
                        if count > 0:
                            st.metric(
                                node_type["label"], 
                                count,
                                label_visibility="visible"
                            )
                        else:
                            st.metric(
                                node_type["label"], 
                                0,
                                label_visibility="visible",
                                delta_color="off"
                            )
                
                st.divider()
                total = node_stats.get("total_nodes", 0)
                st.metric("📊 **Total Nodes**", total)
                
                # Show breakdown percentages
                if total > 0:
                    st.caption("**Node Distribution:**")
                    for node_type in all_node_types:
                        count = node_stats.get(node_type["key"], 0)
                        if count > 0:
                            percentage = (count / total) * 100
                            st.write(f"  • {node_type['label']}: {count} ({percentage:.1f}%)")
            else:
                st.info("ℹ️ No node data available - index a repository first")
        
        # ====================================================================
        # ALL RELATIONSHIP TYPES (8 types)
        # ====================================================================
        with st.expander("🔗 All Relationship Types (8 types)", expanded=False):
            relationships = get_all_relationships()
            
            # Define expected relationships
            expected_relationships = [
                {"type": "CONTAINS", "description": "Module/Class contains code"},
                {"type": "IMPORTS", "description": "Import statement"},
                {"type": "INHERITS_FROM", "description": "Class inheritance"},
                {"type": "CALLS", "description": "Function call"},
                {"type": "DECORATED_BY", "description": "Decorator applied"},
                {"type": "HAS_PARAMETER", "description": "Function parameter"},
                {"type": "DOCUMENTED_BY", "description": "Docstring documentation"},
                {"type": "DEPENDS_ON", "description": "Dependency relationship"},
            ]
            
            if relationships:
                # Create relationship cards
                rel_dict = {r['type']: r['count'] for r in relationships}
                
                for rel_def in expected_relationships:
                    rel_type = rel_def["type"]
                    count = rel_dict.get(rel_type, 0)
                    
                    # Create a nice card for each relationship
                    col_rel, col_count, col_desc = st.columns([0.3, 0.2, 0.5])
                    
                    with col_rel:
                        if count > 0:
                            st.metric(
                                rel_type,
                                count,
                                label_visibility="collapsed"
                            )
                        else:
                            st.write(f"⚪ {rel_type}")
                    
                    with col_count:
                        st.write(f"`{count}`" if count > 0 else "`0`")
                    
                    with col_desc:
                        st.caption(rel_def["description"])
                
                st.divider()
                total_rels = sum(r['count'] for r in relationships)
                st.metric("📊 **Total Relationships**", total_rels)
                
                # Show which relationships exist
                st.caption("**Detected Relationships:**")
                found_rels = [r['type'] for r in relationships]
                for rel_def in expected_relationships:
                    if rel_def["type"] in found_rels:
                        st.write(f"  ✅ {rel_def['type']}")
                    else:
                        st.write(f"  ⚪ {rel_def['type']} (not found)")
                        
            else:
                st.info("ℹ️ No relationships found - index a repository first")
        # ====================================================================
        # INDEXED REPOSITORIES
        # ====================================================================
        st.subheader("📦 Indexed Repositories")
        
        indexed_repos = get_indexed_repos()
        
        if indexed_repos:
            for repo in indexed_repos:
                with st.container(border=True):
                    st.markdown(f"**{repo['name']}**")
                    st.caption(f"🔗 `{repo['url']}`")
                    col1, col2 = st.columns(2)
                    with col1:
                        st.metric("Nodes", repo['nodes'], label_visibility="collapsed")
                    with col2:
                        st.metric("Date", repo['indexed_date'], label_visibility="collapsed")
        else:
            st.info("ℹ️ No repositories indexed yet")
        
        st.divider()
        
        # ====================================================================
        # EMBEDDED REPOSITORIES
        # ====================================================================
        st.subheader("⚡ Embedded Repositories")
        
        embedded_repos = get_embedded_repos()
        
        if embedded_repos:
            for repo in embedded_repos:
                with st.container(border=True):
                    st.markdown(f"**{repo['name']}**")
                    col1, col2 = st.columns(2)
                    with col1:
                        st.metric("Chunks", repo['chunks'], label_visibility="collapsed")
                    with col2:
                        st.metric("Date", repo['embedded_date'], label_visibility="collapsed")
        else:
            st.info("ℹ️ No repositories embedded yet")

    if st.session_state.get("indexing_active", False):
        st.markdown("### 📦 Indexing Progress")
        
        progress_placeholder = st.empty()
        status_container = st.container()
        
        try:
            index_url = st.session_state.get("last_repo_url")
            
            if index_url:
                with progress_placeholder:
                    st.progress(25, text="Sending indexing request...")
                
                with status_container:
                    with st.spinner("Indexing repository to Neo4j..."):
                        index_res = requests.post(
                            f"{GATEWAY_URL}/api/chat",
                            json={"query": f"Index this repository: {index_url}"},
                            timeout=300
                        )
                
                if index_res.ok:
                    index_data = index_res.json()
                    
                    with progress_placeholder:
                        st.progress(100, text="Indexing Complete!")
                    
                    with status_container:
                        if index_data.get("success"):
                            st.success("✅ Repository Indexed Successfully!")
                            st.write(f"**Response:** {index_data.get('response', 'Indexing complete')}")
                            
                            st.session_state.indexing_active = False
                            st.session_state.embeddings_created = True
                            time.sleep(2)
                            st.rerun()
                        else:
                            st.error(f"⚠️ Indexing failed: {index_data.get('error', 'Unknown error')}")
                            st.session_state.indexing_active = False
                else:
                    with status_container:
                        st.error(f"⚠️ Indexing failed: {index_res.text}")
                    st.session_state.indexing_active = False
                    
        except requests.exceptions.Timeout:
            with status_container:
                st.error("⏱️ Indexing timeout - large repository")
            st.session_state.indexing_active = False
        except Exception as e:
            with status_container:
                st.error(f"❌ Error: {str(e)}")
            st.session_state.indexing_active = False
        
        st.stop()  # Show Embedding Progress - ONLY when embedding_active is True
    if st.session_state.get("embedding_active", False):
        st.markdown("### ⚡ Embedding Progress")
        
        progress_placeholder = st.empty()
        status_container = st.container()
        
        try:
            embed_url = st.session_state.get("last_repo_url")
            repo_id = embed_url.split("/")[-1] if embed_url else "fastapi"  # Extract repo name
            
            if embed_url:
                with progress_placeholder:
                    st.progress(25, text="Sending embedding request...")
                
                with status_container:
                    with st.spinner("Embedding repository to Pinecone..."):
                        embed_res = requests.post(
                            f"{ORCHESTRATOR_SERVICE}/execute",
                            json={
                                "query": f"Embed this repository: {embed_url} with repo_id: {repo_id}"
                            },
                            timeout=300
                        )
                
                if embed_res.ok:
                    embed_data = embed_res.json()
                    
                    with progress_placeholder:
                        st.progress(100, text="Embedding Complete!")
                    
                    with status_container:
                        if embed_data.get("success") or (embed_data.get("data") and not embed_data.get("error")):
                            response_msg = embed_data.get("response") or embed_data.get("data", {}).get("statistics", {})
                            st.success("✅ Repository Embedded Successfully!")
                            st.write(f"**Response:** {response_msg}")
                            
                            st.session_state.embedding_active = False
                            st.session_state.embeddings_created = True
                            time.sleep(2)
                            st.rerun()
                        else:
                            st.error(f"⚠️ Embedding failed: {embed_data.get('error', 'Unknown error')}")
                            st.session_state.embedding_active = False
                else:
                    with status_container:
                        st.error(f"⚠️ Embedding failed: {embed_res.text}")
                    st.session_state.embedding_active = False
                        
        except requests.exceptions.Timeout:
            with status_container:
                st.error("⏱️ Embedding timeout - large repository")
            st.session_state.embedding_active = False
        except Exception as e:
            with status_container:
                st.error(f"❌ Error: {str(e)}")
            st.session_state.embedding_active = False
        
        st.stop()  # Stop execution here after embedding# ← CRITICAL: Stop execution here after indexing
        
    

# Main chat area - only renders when NOT indexing
st.title("Agentic Codebase Chat")

# MODE SELECTOR
col_mode1, col_mode2, col_spacer = st.columns([1, 1, 3])
with col_mode1:
    chat_mode = st.radio(
        "Chat Mode",
        ["Agentic AI"],
        horizontal=True,
        key="chat_mode_selector"
    )

st.info("✨ **Agentic AI Mode**: GPT-4 autonomously reasons and chains tools. Shows thinking process.")

st.markdown("### Conversation History")

message_container = st.container()
with message_container:
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.write(msg["content"])
            
            if msg["role"] == "assistant":
                # Store response data from last API call
                response_data = msg.get("response_data", {})
                retrieved_sources = response_data.get("retrieved_sources", [])
                sources_count = response_data.get("sources_count", 0)
                scenario = response_data.get("scenario", "unknown")
                reranked = response_data.get("reranked_results", False)
                
                # AGENTIC AI MESSAGE
                if "thinking_process" in msg:
                    thinking_steps = msg.get("thinking_process", [])
                    tools_used = msg.get("tools_used", [])
                    iterations = msg.get("iterations", 0)
                    
                    st.divider()
                    
                    with st.expander(f"🧠 Thinking Process ({iterations} iterations)", expanded=False):
                        for i, step in enumerate(thinking_steps, 1):
                            st.caption(f"**Step {i}:** {step[:300]}...")
                
                # SHOW RETRIEVED SOURCES FROM MESSAGE HISTORY
                if retrieved_sources:
                    pinecone_sources = [s for s in retrieved_sources if s.get('source_type') == 'pinecone']
                    neo4j_sources = [s for s in retrieved_sources if s.get('source_type') == 'neo4j']   
                    if pinecone_sources:
                        st.write("**📝 Code Chunks (Semantic Search)**")
                        for j, source in enumerate(pinecone_sources, 1):
                            # Use DIFFERENT keys for button and state
                            msg_idx = len(st.session_state.messages)
                            button_key = f"history_btn_msg{msg_idx}_{j}"     # ← Button key (read-only)
                            state_key = f"history_state_msg{msg_idx}_{j}"   # ← State key (writable)
                            
                            # Initialize state BEFORE creating widget
                            if state_key not in st.session_state:
                                st.session_state[state_key] = False
                            
                            with st.container(border=True):
                                col1, col2 = st.columns([0.8, 0.2])
                                
                                with col1:
                                    st.markdown(f"""
                                                    **{j}. {source.get('file_name', 'unknown')}**
                                                    - **Language:** {source.get('language', 'python')}
                                                    - **Lines:** {source.get('start_line', '?')}-{source.get('end_line', '?')}
                                                    - **Relevance:** {round(source.get('relevance_score', 0) * 100)}% {'(reranked)' if source.get('reranked') else ''}
                                                                                            """)
                                    
                                with col2:
                                    # Button click toggles the state
                                    if st.button("📂 View", key=button_key):
                                        st.session_state[state_key] = not st.session_state[state_key]
                            
                            # Display code if toggled on
                            if st.session_state.get(state_key):
                                st.code(source.get('content', 'No content'), language=source.get('language', 'python'))
                                    
                    if neo4j_sources:  # ← CORRECT: Now at proper indentation level
                        st.write("**🔗 Neo4j Knowledge Graph**")
                        
                        # Separate entity and relationship sources
                        entity_sources = [s for s in neo4j_sources if s.get("type") == "entity"]
                        rel_sources = [s for s in neo4j_sources if s.get("type") == "relationships"]
                        
                        # Display entities
                        if entity_sources:
                            st.markdown("##### 📋 **Entities**")
                            for k, source in enumerate(entity_sources, 1):
                                with st.container(border=True):
                                    st.markdown(f"""
**{source.get('entity_type', 'Unknown')}:** `{source.get('entity_name', 'unknown')}`
- **Module:** {source.get('module', 'N/A')}
- **Line:** {source.get('line_number', 'N/A')}
                                    """)
                        
                        # Display relationships
                        if rel_sources:
                            st.markdown("##### 🔗 **Dependent Entities (Things that depend on this)**")
                            for k, rel_source in enumerate(rel_sources, 1):
                                entity_name = rel_source.get("entity_name", "Unknown")
                                entity_type = rel_source.get("entity_type", "Unknown")
                                dependents = rel_source.get("dependents", [])
                                dependents_count = rel_source.get("dependents_count", 0)
                                
                                with st.container(border=True):
                                    st.markdown(f"""
**{entity_name}** (`{entity_type}`)
**Total Dependents:** {dependents_count}
                                    """)
                                    
                                    if dependents:
                                        st.markdown("**List of entities that depend on this:**")
                                        
                                        # Display dependents in columns for better layout
                                        cols = st.columns(2)
                                        for idx, dependent in enumerate(dependents[:10]):  # Show top 10
                                            col = cols[idx % 2]
                                            with col:
                                                dep_name = dependent.get("name", "Unknown")
                                                dep_type = dependent.get("type", "Unknown")
                                                relation_type = dependent.get("relation", "USES")
                                                
                                                st.write(f"  • `{dep_name}` ({dep_type})")
                                                st.caption(f"    ↳ {relation_type}")
                                        
                                        if len(dependents) > 10:
                                            st.caption(f"... and {len(dependents) - 10} more")
                                    else:
                                        st.info("ℹ️ No dependents found")
                                                            
                    if tools_used:
                        st.write("**🔧 Tools Used:**")
                        tool_str = " ".join([f'<span class="agent-badge">{t}</span>' for t in tools_used])
                        st.markdown(tool_str, unsafe_allow_html=True)

st.divider()

# CHAT INPUT
query = st.chat_input("Ask about the codebase... (or 'Index https://...' or 'Embed https://...')")

if query:
    # ====================================================================
    # DETECT INDEXING/EMBEDDING COMMANDS
    # ====================================================================
    
    # Check if query is an indexing or embedding request
    query_lower = query.lower()
    is_index_request = any(keyword in query_lower for keyword in ["index", "indexed", "indexing"])
    is_embed_request = any(keyword in query_lower for keyword in ["embed", "embedding", "embedded"])
    
    # Extract GitHub URL from query
    extracted_url = None
    if "http" in query_lower:
        # Extract URL between spaces or at end
        import re
        urls = re.findall(r'https?://[^\s]+', query)
        if urls:
            extracted_url = urls[0].rstrip('.,;:')
    
    # HANDLE INDEXING REQUEST
    if is_index_request and extracted_url:
        with st.chat_message("user"):
            st.write(query)
        
        st.session_state.messages.append({"role": "user", "content": query})
        
        # Create modal popup
        col_left, col_popup, col_right = st.columns([1, 2, 1])
        
        with col_popup:
            
            st.markdown("## 📦 Indexing Repository to Neo4j")
            st.info(f"📌 Repository: `{extracted_url}`")
            
            progress_bar = st.progress(0, text="Preparing...")
            status_placeholder = st.empty()
            
            try:
                with status_placeholder:
                    st.info("⏳ Sending indexing request to Neo4j...")
                
                progress_bar.progress(25, text="Processing repository...")
                
                index_res = requests.post(
                    f"{GATEWAY_URL}/api/chat",
                    json={"query": f"Index this repository: {extracted_url}"},
                    timeout=300
                )
                
                if index_res.ok:
                    index_data = index_res.json()
                    
                    if index_data.get("success"):
                        progress_bar.progress(100, text="✅ Indexing Complete!")
                        with status_placeholder:
                            st.success("✅ Repository indexed successfully!")
                            st.write(f"**Response:** {index_data.get('response', 'Indexing complete')[:300]}")
                        
                        time.sleep(2)
                        st.session_state.neo4j_stats = None  # Clear cache to refresh stats
                        
                        # Store in messages
                        st.session_state.messages.append({
                            "role": "assistant",
                            "content": "✅ Repository has been successfully indexed to Neo4j!",
                            "thinking_process": [
                                "Detected indexing request",
                                f"Repository: {extracted_url}",
                                "Indexing to Neo4j completed"
                            ],
                            "tools_used": ["index_repository"],
                            "iterations": 3,
                            "retrieved_context": [],
                            "response_data": {
                                "retrieved_sources": [],
                                "sources_count": 0,
                                "scenario": "admin",
                                "reranked_results": False
                            }
                        })
                        
                        st.markdown("</div>", unsafe_allow_html=True)
                        st.rerun()
                    else:
                        progress_bar.progress(0, text="❌ Indexing Failed!")
                        with status_placeholder:
                            st.error(f"❌ Indexing failed: {index_data.get('error', 'Unknown error')}")
                        st.markdown("</div>", unsafe_allow_html=True)
                else:
                    progress_bar.progress(0, text="❌ Indexing Failed!")
                    with status_placeholder:
                        st.error(f"❌ Indexing failed: {index_res.text}")
                    st.markdown("</div>", unsafe_allow_html=True)
                    
            except requests.exceptions.Timeout:
                progress_bar.progress(0, text="❌ Timeout!")
                with status_placeholder:
                    st.error("⏱️ Indexing timeout - repository too large")
                st.markdown("</div>", unsafe_allow_html=True)
            except Exception as e:
                progress_bar.progress(0, text="❌ Error!")
                with status_placeholder:
                    st.error(f"❌ Error: {str(e)}")
                st.markdown("</div>", unsafe_allow_html=True)
        
        st.stop()
    
    # HANDLE EMBEDDING REQUEST
    elif is_embed_request and extracted_url:
        with st.chat_message("user"):
            st.write(query)
        
        st.session_state.messages.append({"role": "user", "content": query})
        
        # Create modal popup
        col_left, col_popup, col_right = st.columns([1, 2, 1])
        
        with col_popup:
            
            st.markdown("## ⚡ Embedding Repository to Pinecone")
            st.info(f"📌 Repository: `{extracted_url}`")
            
            progress_bar = st.progress(0, text="Preparing...")
            status_placeholder = st.empty()
            
            try:
                with status_placeholder:
                    st.info("⏳ Sending embedding request to Pinecone...")
                
                progress_bar.progress(25, text="Processing repository...")
                
                repo_id = extracted_url.split("/")[-1].replace(".git", "")
                
                embed_res = requests.post(
                    f"{GATEWAY_URL}/api/chat",
                    json={"query": f"Embed this repository: {extracted_url} with repo_id: {repo_id}"},
                    timeout=300
                )
                
                if embed_res.ok:
                    embed_data = embed_res.json()
                    
                    if embed_data.get("success"):
                        progress_bar.progress(100, text="✅ Embedding Complete!")
                        with status_placeholder:
                            st.success("✅ Repository embedded successfully!")
                            st.write(f"**Response:** {embed_data.get('response', 'Embedding complete')[:300]}")
                        
                        time.sleep(2)
                        st.session_state.pinecone_stats = None  # Clear cache to refresh stats
                        
                        # Store in messages
                        st.session_state.messages.append({
                            "role": "assistant",
                            "content": "✅ Repository has been successfully embedded to Pinecone!",
                            "thinking_process": [
                                "Detected embedding request",
                                f"Repository: {extracted_url}",
                                f"Repo ID: {repo_id}",
                                "Embedding to Pinecone completed"
                            ],
                            "tools_used": ["embed_repository"],
                            "iterations": 4,
                            "retrieved_context": [],
                            "response_data": {
                                "retrieved_sources": [],
                                "sources_count": 0,
                                "scenario": "admin",
                                "reranked_results": False
                            }
                        })
                        
                        st.markdown("</div>", unsafe_allow_html=True)
                        st.rerun()
                    else:
                        progress_bar.progress(0, text="❌ Embedding Failed!")
                        with status_placeholder:
                            st.error(f"❌ Embedding failed: {embed_data.get('error', 'Unknown error')}")
                        st.markdown("</div>", unsafe_allow_html=True)
                else:
                    progress_bar.progress(0, text="❌ Embedding Failed!")
                    with status_placeholder:
                        st.error(f"❌ Embedding failed: {embed_res.text}")
                    st.markdown("</div>", unsafe_allow_html=True)
                    
            except requests.exceptions.Timeout:
                progress_bar.progress(0, text="❌ Timeout!")
                with status_placeholder:
                    st.error("⏱️ Embedding timeout - repository too large")
                st.markdown("</div>", unsafe_allow_html=True)
            except Exception as e:
                progress_bar.progress(0, text="❌ Error!")
                with status_placeholder:
                    st.error(f"❌ Error: {str(e)}")
                st.markdown("</div>", unsafe_allow_html=True)
        
        st.stop()
    
    # NORMAL CHAT QUERY
    else:
        with st.chat_message("user"):
            st.write(query)
        
        st.session_state.messages.append({"role": "user", "content": query})

        try:
            with st.chat_message("assistant"):
                # Agentic AI Mode
                with st.spinner("🧠 Orchestrator is analyzing and chaining tools..."):
                    payload = {
                        "query": query,
                        "session_id": st.session_state.session_id
                    }
                    
                    res = requests.post(
                        f"{GATEWAY_URL}/api/chat",
                        json=payload,
                        timeout=120
                    )
                
            if res.ok:
                data = res.json()
                    
                if data.get("success"):
                        # DEBUG: Print the full response
                        st.write("DEBUG - Full Response:")
                        st.json(data)
                        answer = data.get("response", "No response generated")
                        intent = data.get("intent", "search")
                        entities_found = data.get("entities_found", [])
                        agents_used = data.get("agents_used", [])
                        session_id = data.get("session_id")
                        
                        # Extract sources from the correct location
                        retrieved_sources = data.get("retrieved_sources", [])
                        sources_count = data.get("sources_count", 0)
                        reranked_results = data.get("reranked_results", False)
                        scenario = data.get("scenario", "unknown")
                        
                        if session_id:
                            st.session_state.session_id = session_id
                        
                        # Display answer with streaming effect
                        message_placeholder = st.empty()
                        displayed_text = ""
                        for char in answer:
                            displayed_text += char
                            message_placeholder.write(displayed_text)
                            time.sleep(0.01)
                        
                        st.divider()
                        
                        # SHOW THINKING PROCESS
                        thinking_steps = [
                            f"Intent: {intent}",
                            f"Entities: {', '.join(entities_found) if entities_found else 'None'}",
                            f"Agents routed: {', '.join(agents_used) if agents_used else 'None'}"
                        ]
                        
                        with st.expander(f"🧠 Thinking Process ({len(thinking_steps)} steps)", expanded=False):
                            for i, step in enumerate(thinking_steps, 1):
                                st.caption(f"**Step {i}:** {step}")
                        
                        # ========================================================================
                        # SOURCES SECTION - Display Neo4j and Pinecone sources
                        # ======================================================================== 
                        st.divider()
                        
                        if retrieved_sources and sources_count > 0:
                            st.markdown(f"### 📚 **Retrieved Sources** ({sources_count} found)")
                            
                            # Separate sources by type
                            pinecone_sources = [s for s in retrieved_sources if s.get("source_type") == "pinecone"]
                            neo4j_sources = [s for s in retrieved_sources if s.get("source_type") == "neo4j"]
                            
                            # Display metadata
                            col1, col2, col3 = st.columns(3)
                            with col1:
                                st.metric("📍 Code Chunks", len(pinecone_sources))
                            with col2:
                                st.metric("🔗 Graph Entities", len(neo4j_sources))
                            with col3:
                                rerank_badge = "✅ Reranked" if reranked_results else "📊 Semantic"
                                st.metric("🤖 AI Method", rerank_badge)
                            
                            st.caption(f"Scenario: `{scenario}` | Total: {sources_count} sources")
                            
                            # ====================================================================
                            # NEO4J SOURCES (Entity relationships from knowledge graph)
                            # ====================================================================
                            if neo4j_sources:
                                st.markdown("#### 🔗 **Neo4j Knowledge Graph - Entity Information**")
                                
                                for idx, source in enumerate(neo4j_sources, 1):
                                    with st.container(border=True):
                                        col_info, col_expand = st.columns([0.9, 0.1])
                                        
                                        with col_info:
                                            entity_name = source.get("entity_name", "Unknown")
                                            entity_type = source.get("entity_type", "Unknown")
                                            module = source.get("module", "N/A")
                                            line_num = source.get("line_number", "N/A")
                                            
                                            st.markdown(f"""
                **{entity_name}** `{entity_type}`
                - **Module:** `{module}`
                - **Line:** {line_num}
                - **Type:** {entity_type}
                                            """)
                                        
                                        # Use DIFFERENT keys for button and state
                                        session_key = str(st.session_state.session_id) if st.session_state.session_id else "new"
                                        button_key = f"neo4j_btn_{session_key}_{idx}"      # ← Button key (read-only)
                                        state_key = f"neo4j_state_{session_key}_{idx}"    # ← State key (writable)
                                        
                                        # Initialize state BEFORE creating widget
                                        if state_key not in st.session_state:
                                            st.session_state[state_key] = False
                                        
                                        with col_expand:
                                            # Button click toggles the state
                                            if st.button("📖", key=button_key, help="View details"):
                                                st.session_state[state_key] = not st.session_state[state_key]
                                        
                                        # Display JSON if toggled on
                                        if st.session_state.get(state_key, False):
                                            st.json(source.get("properties", {}), expanded=False)
                            
                            # ====================================================================
                            # PINECONE SOURCES (Code chunks from semantic search)
                            # ====================================================================
                            if pinecone_sources:
                                st.markdown("#### 🔍 **Pinecone Semantic Search - Code Snippets**")
                                
                                for idx, chunk in enumerate(pinecone_sources, 1):
                                    with st.container(border=True):
                                        col_file, col_score, col_expand = st.columns([0.6, 0.2, 0.2])
                                        
                                        with col_file:
                                            file_name = chunk.get("file_name", "unknown")
                                            start_line = chunk.get("start_line", 0)
                                            end_line = chunk.get("end_line", 0)
                                            language = chunk.get("language", "python")
                                            
                                            st.markdown(f"""
                                        📄 **{file_name}**
                                        - **Lines:** {start_line}-{end_line}
                                        - **Language:** `{language}`
                                                                    """)
                                                                                                    
                                        with col_score:
                                            relevance = chunk.get("relevance_score", 0)  # DECIMAL: 0.433
                                            confidence = chunk.get("confidence", 0)  # DECIMAL: 0.433
                                            reranked_badge = "✅ Reranked" if chunk.get("reranked") else "📊 Semantic"
                                            
                                            # Convert decimal to percentage for display
                                            relevance_percent = relevance * 100 if relevance else 0
                                            
                                            st.write(f"**Relevance:** {relevance_percent:.1f}%")
                                            st.write(f"**Confidence:** {confidence:.1%}")
                                            st.caption(f"{reranked_badge}")
                                        
                                        # Use DIFFERENT keys for button and state
                                        session_key = str(st.session_state.session_id) if st.session_state.session_id else "new"
                                        button_key = f"pinecone_btn_{session_key}_{idx}"      # ← Button key (read-only)
                                        state_key = f"pinecone_state_{session_key}_{idx}"    # ← State key (writable)
                                        
                                        # Initialize state BEFORE creating widget
                                        if state_key not in st.session_state:
                                            st.session_state[state_key] = False
                                        
                                        with col_expand:
                                            # Button click toggles the state
                                            if st.button("💻 View", key=button_key, help="View code"):
                                                st.session_state[state_key] = not st.session_state[state_key]

                                        # Display code if toggled on
                                        if st.session_state.get(state_key, False):
                                            code_content = chunk.get("content") or chunk.get("preview", "")
                                            language = chunk.get("language", "python")
                                            
                                            st.markdown("---")
                                            st.markdown(f"**📝 Code from {chunk.get('file_name', 'unknown')} (Lines {chunk.get('start_line', '?')}-{chunk.get('end_line', '?')})**")
                                            
                                            if code_content and code_content.strip():
                                                st.code(code_content, language=language)
                                            else:
                                                st.warning("⚠️ No code content available for this chunk")
                            
                            else:
                                st.info("ℹ️ No sources retrieved for this query")
                            st.divider()

                        # Store in session state
                        st.session_state.messages.append({
                            "role": "assistant",
                            "content": answer,
                            "thinking_process": thinking_steps,
                            "tools_used": agents_used,
                            "iterations": len(thinking_steps),
                            "retrieved_context": [],
                            "response_data": {
                                "retrieved_sources": retrieved_sources,
                                "sources_count": sources_count,
                                "scenario": scenario,
                                "reranked_results": reranked_results
                            }
                        })
                        st.rerun()
                else:
                    st.error(f"Error: {data.get('error', 'Unknown error')}")
                    st.session_state.messages.append({"role": "assistant", "content": f"Error: {data.get('error', 'Unknown error')}"})
                    st.rerun()
            else:
                st.error(f"Error: {res.text}")

        except requests.exceptions.Timeout:
            st.error("⏱️ Request timeout")
        except Exception as e:
            st.error(f"Error: {str(e)}")



# ============================================================================
# TAB 2: KNOWLEDGE GRAPH
# ============================================================================
# with tab_graph:
#     st.header("Knowledge Graph Visualization")
    
#     st.subheader("Select Node Type at Specific Node")
    
#     def get_all_entities():
#         """Fetch all entities grouped by type - includes Functions, Methods, Parameters, etc."""
#         try:
#             # Query ALL node types (Class, Function, Method, Parameter, Type, Package, File, Docstring)
#             cypher = """
#             MATCH (e)
#             WHERE e.name IS NOT NULL
#             WITH labels(e)[0] as node_type, e.name as name
#             RETURN node_type, name
#             ORDER BY node_type, name
#             LIMIT 5000
#             """
#             response = requests.post(
#                 f"{GATEWAY_URL}/api/chat",
#                 json={"query": f"Execute this Cypher query: {cypher}"},
#                 timeout=10
#             )
#             if response.ok:
#                 data = response.json()
#                 results = data.get("data", {}).get("query_results", []) if data.get("success") else []
#                 entities_dict = {}
#                 for r in results:
#                     node_type = r.get("node_type", "Unknown")
#                     name = r.get("name", "")
                    
#                     # Skip empty names
#                     if not name:
#                         continue
                    
#                     # For Functions + Methods: combine into "Function/Method"
#                     if node_type == "Method":
#                         display_type = "Function/Method"
#                     else:
#                         display_type = node_type
                    
#                     if display_type not in entities_dict:
#                         entities_dict[display_type] = []
#                     entities_dict[display_type].append(name)
                
#                 # Remove duplicates and sort
#                 for key in entities_dict:
#                     entities_dict[key] = sorted(set(entities_dict[key]))
                
#                 return entities_dict
#         except Exception as e:
#             st.error(f"Error fetching entities: {str(e)}")
#         return {}
    
#     entities_by_type = get_all_entities()
    
#     if not entities_by_type:
#         st.warning("No entities found. Index a repository first.")
#     else:
#         # DUAL DROPDOWNS: Node Type â†’ Specific Nodes with SEARCH
#         col1, col2, col3 = st.columns([2, 2, 1])
        
#         with col1:
#             selected_type = st.selectbox(
#                 "1 Node Type",
#                 options=["Select a type..."] + sorted(list(entities_by_type.keys())),
#                 key="type_select"
#             )
        
#         with col2:
#             if selected_type and selected_type != "Select a type...":
#                 entity_list = entities_by_type.get(selected_type, [])
                
#                 # ” Add search bar for filtering large lists
#                 search_term = st.text_input(
#                     f"Search {selected_type}s ({len(entity_list)} available)",
#                     placeholder="Type to filter...",
#                     key="entity_search"
#                 )
                
#                 # Filter list based on search
#                 if search_term:
#                     filtered_list = [e for e in entity_list if search_term.lower() in e.lower()]
#                 else:
#                     filtered_list = entity_list
                
#                 if filtered_list:
#                     entity_name = st.selectbox(
#                         f"2 Select {selected_type}",
#                         options=filtered_list,
#                         key="entity_select"
#                     )
#                 else:
#                     st.warning(f"No {selected_type} found matching '{search_term}'")
#                     entity_name = None
#             else:
#                 st.selectbox(
#                     "2 Select type first",
#                     options=["No type selected"],
#                     disabled=True,
#                     key="entity_select_disabled"
#                 )
#                 entity_name = None
        
#         with col3:
#             visualize_button = st.button("Visualize", use_container_width=True, disabled=(entity_name is None))
        
#         if visualize_button and entity_name:
#             # ¤– AI-POWERED VISUALIZATION PIPELINE WITH MULTIPLE CYPHER QUERIES
#             with st.spinner(f"Step 1: Generating optimized Cypher queries for {selected_type}..."):
#                 try:
#                     # STEP 1: Generate MULTIPLE Cypher queries based on node type and relationships
#                     cypher_queries = get_cypher_query_templates(selected_type, entity_name)
                    
#                     st.info(f" Generated {len(cypher_queries)} optimized Cypher queries")
#                     st.caption(f" {get_query_description(selected_type)}")
                    
#                 except Exception as e:
#                     st.error(f"Step 1 failed: {str(e)}")
#                     st.stop()
            
#             # Display the generated queries in an expander
#             # Display the generated queries in an expander
#             with st.expander(f"🔍 Generated Cypher Queries for {entity_name}", expanded=False):
#                 for i, q in enumerate(cypher_queries, 1):
#                     st.code(q, language="cypher")
            
#             # STEP 2: Execute ALL Cypher queries and collect results
#             all_results = []
#             query_status_list = []
            
#             with st.spinner(f"Step 2: Executing {len(cypher_queries)} queries on Neo4j..."):
#                 try:
#                     progress_bar = st.progress(0)
                    
#                     for idx, query in enumerate(cypher_queries, 1):
#                         try:
#                             cypher_exec_response = requests.post(
#                                 f"{GATEWAY_URL}/api/chat",
#                                 json={
#                                     "query": f"Execute Cypher query for {entity_name}: {query}"
#                                 },
#                                 timeout=20
#                             )
#                             if cypher_exec_response.ok:
#                                 exec_data = cypher_exec_response.json()
#                                 results = exec_data.get("data", {}).get("query_results", []) if exec_data.get("success") else []
#                                 all_results.extend(results)
#                                 query_status_list.append({
#                                     "Query": idx,
#                                     "Status": " Success",
#                                     "Results": len(results)
#                                 })
#                             else:
#                                 query_status_list.append({
#                                     "Query": idx,
#                                     "Status": " Failed",
#                                     "Results": 0
#                                 })
#                         except Exception as q_error:
#                             query_status_list.append({
#                                 "Query": idx,
#                                 "Status": " Error",
#                                 "Results": 0
#                             })
                        
#                         # Update progress
#                         progress_bar.progress(idx / len(cypher_queries))
                    
#                     progress_bar.empty()
                    
#                     if not all_results:
#                         st.warning(f"No relationships found for {entity_name}")
#                         # Show query status for debugging
#                         import pandas as pd
#                         status_df = pd.DataFrame(query_status_list)
#                         st.dataframe(status_df, use_container_width=True)
#                         st.stop()
                    
#                     st.success(f" All {len(cypher_queries)} queries executed - {len(all_results)} total results")
                    
#                    # Show query status summary (text only, no dataframe)
#                     with st.expander(" Query Execution Status"):
#                         for status in query_status_list:
#                             query_num = status.get("Query", "?")
#                             status_icon = "✅" if status.get("Status") == " Success" else "❌"
#                             results = status.get("Results", 0)
#                             st.write(f"{status_icon} Query {query_num}: {results} results")
                    
#                 except Exception as e:
#                     st.error(f"Step 2 failed: {str(e)}")
#                     st.stop()
            

#             # STEP 2.5: Display query results in a table
#             with st.expander(f"📊 All Query Results ({len(all_results)} results)", expanded=False):
#                 if all_results:
#                     # Display as JSON instead of dataframe (avoids pyarrow issues)
#                     st.json(all_results[:5])  # Show first 5 results
#                     if len(all_results) > 5:
#                         st.caption(f"... and {len(all_results) - 5} more results")
#                 else:
#                     st.warning("No results to display")
            
            
#             # STEP 3: Call generate_mermaid tool on Orchestrator
#             st.divider()

#             with st.spinner(f"⏳ Step 3: Generating Mermaid diagram..."):
#                 try:
#                     # Call generate_mermaid tool directly on Orchestrator
#                     mermaid_response = requests.post(
#                         f"{ORCHESTRATOR_SERVICE}/execute",
#                         json={
#                             "tool_name": "generate_mermaid",
#                             "tool_input": {
#                                 "query_results": all_results,
#                                 "entity_name": entity_name,
#                                 "entity_type": selected_type
#                             }
#                         },
#                         timeout=60
#                     )
                    
#                     if mermaid_response.ok:
#                         mermaid_data = mermaid_response.json()
                        
#                         # Extract mermaid_code from ToolResult response
#                         mermaid_code = ""
#                         if mermaid_data.get("success"):
#                             mermaid_code = mermaid_data.get("data", {}).get("mermaid_code", "")
#                         elif isinstance(mermaid_data, dict) and "data" in mermaid_data:
#                             mermaid_code = mermaid_data.get("data", {}).get("mermaid_code", "")
                        
#                         if mermaid_code and mermaid_code.strip():
#                             st.success("✅ Diagram generated!")
#                             st.divider()
                            
#                             # Render with proper error handling
#                             try:
#                                 render_mermaid_diagram(mermaid_code, height=600, diagram_title=f"📊 {entity_name} Relationships")
#                             except Exception as render_err:
#                                 st.warning(f"Mermaid rendering issue: {str(render_err)[:100]}")
#                                 st.info("**Mermaid Code (for debugging):**")
#                                 st.code(mermaid_code, language="mermaid")
#                         else:
#                             st.warning("No diagram code generated")
#                             st.info(f"Query returned {len(all_results)} results but Mermaid tool produced no diagram")
#                     else:
#                         st.error(f"Mermaid tool failed: {mermaid_response.text}")
#                 except Exception as e:
#                     st.error(f"❌ Failed to call Mermaid tool: {str(e)}")

# ============================================================================
# TAB 3: TOOLS
# ============================================================================
with tab_tools:
    st.title("Tools & Utilities")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("System Health")
        try:
            health_res = requests.get(f"{GATEWAY_URL}/health", timeout=5)
            if health_res.ok:
                health_data = health_res.json()
                status = health_data.get("status", "unknown")
                
                if status == "healthy":
                    st.success("✓ System Healthy")
                else:
                    st.error("System Unhealthy")
                
                services = health_data.get("services", {})
                for service_name, service_status in services.items():
                    service_ok = service_status.get("status") == "healthy"
                    icon = "✓" if service_ok else "✗"
                    st.write(f"{icon} {service_name}: {'ok' if service_ok else 'error'}")
        except Exception as e:
            st.error(f"Error: {str(e)}")
    
    with col2:
        st.subheader("Database Management")
        st.warning("⚠️ This will delete ALL indexed data!")
        
        if st.checkbox("I understand", key="confirm_clear"):
            if st.button("🗑️ Clear Database"):
                try:
                    res = requests.post(
                        f"{GATEWAY_URL}/api/chat",
                        json={"query": "Clear and delete all indexed data from the database"},
                        timeout=30
                    )
                    if res.ok:
                        data = res.json()
                        if data.get("success"):
                            st.success("✅ Database cleared!")
                            st.balloons()
                        else:
                            st.error(f"Error: {data.get('error', 'Unknown error')}")
                except Exception as e:
                    st.error(f"Error: {str(e)}")
    
    st.divider()
    
    # EMBEDDINGS MANAGEMENT
    col3, col4 = st.columns(2)
    
    with col3:
        st.subheader("⚡ Embeddings Management")
        st.warning("⚠️ This will delete ALL Pinecone embeddings!")
        
        if st.checkbox("I understand embeddings deletion", key="confirm_delete_embeddings"):
            repo_id = st.text_input(
                "Repository ID to delete",
                placeholder="fastapi (leave empty for all)",
                key="repo_id_delete"
            )
            
            if st.button("🗑️ Delete Embeddings", use_container_width=True):
                try:
                    with st.spinner("Deleting embeddings..."):
                        delete_repo_id = repo_id if repo_id else "all"
                        
                        delete_res = requests.delete(
                            f"{INDEXER_SERVICE}/embeddings/delete",
                            params={"repo_id": delete_repo_id},
                            timeout=30
                        )
                        
                        if delete_res.ok:
                            delete_data = delete_res.json()
                            if delete_data.get("success"):
                                st.success(f"✅ {delete_data.get('message', 'Embeddings deleted!')}")
                                st.info(f"💡 Deleted from: {delete_data.get('index_name', 'Pinecone')}")
                                time.sleep(2)
                                st.rerun()
                            else:
                                st.error(f"❌ {delete_data.get('error', 'Delete failed')}")
                        else:
                            st.error(f"Delete failed: {delete_res.text}")
                
                except requests.exceptions.Timeout:
                    st.error("⏱️ Delete timeout")
                except Exception as e:
                    st.error(f"Error: {str(e)}")
    
    with col4:
        st.subheader("📊 Embeddings Stats Quick Check")
        if st.button("🔄 Refresh Embeddings Stats", use_container_width=True):
            try:
                stats_res = requests.get(f"{INDEXER_SERVICE}/embeddings/stats", timeout=10)
                if stats_res.ok:
                    stats_data = stats_res.json()
                    if stats_data.get("status") == "available":
                        summary = stats_data.get("summary", {})
                        stats = stats_data.get("stats", {})
                        
                        st.metric("📦 Code Chunks", summary.get("chunks_total", 0))
                        st.metric("🧬 Total Vectors", stats.get("total_vectors", 0))
                        st.metric("📐 Dimension", stats.get("dimension", 0))
                        st.success(f"✅ {summary.get('status', 'Ready')}")
                    else:
                        st.warning(f"⚠️ {stats_data.get('message', 'Pinecone unavailable')}")
            except Exception as e:
                st.warning(f"Could not fetch stats: {str(e)[:50]}")
    
    st.divider()
    
    st.subheader("API Info")
    st.write(f"**Gateway URL:** `{GATEWAY_URL}`")
    st.write(f"**Architecture:** Streamlit → Gateway → Orchestrator → Agents")
    st.write(f"**Session:** `{st.session_state.session_id or 'Not initialized'}`")

    if st.button("View Gateway Endpoints"):
            endpoints = {
                "/health": "System health check",
                "/api/chat": "Chat with orchestrator",
                "/api": "API info",
            }
            st.json(endpoints)