"""
Streamlit UI for Agentic Codebase Chat System.

Multi-agent repository analysis with RAG, visualization, and tools.
"""

import streamlit as st
import streamlit.components.v1 as components
import requests
import time
import os

import re
import sys

sys.path.insert(0, '/mnt/project')

from mermaid_renderer import render_mermaid_diagram
from relationship_mappings import get_cypher_query_templates, get_query_description
from network_graph_renderer import render_network_graph, extract_nodes_and_edges

# Configuration
API_BASE = os.getenv("API_BASE", "http://gateway:8000")
REFRESH_INTERVAL = 3  # seconds

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

# ============================================================================
# INITIALIZE SESSION STATE
# ============================================================================
if "session_id" not in st.session_state:
    st.session_state.session_id = None
if "messages" not in st.session_state:
    st.session_state.messages = []
if "last_auto_refresh" not in st.session_state:
    st.session_state.last_auto_refresh = 0
if "db_stats" not in st.session_state:
    st.session_state.db_stats = {
        "Package": 0,
        "File": 0,
        "Class": 0,
        "Function": 0,
        "Parameter": 0,
        "Type": 0,
    }
if "indexing_active" not in st.session_state:
    st.session_state.indexing_active = False
if "embedding_active" not in st.session_state:
    st.session_state.embedding_active = False
if "embeddings_created" not in st.session_state:
    st.session_state.embeddings_created = False
if "last_repo_url" not in st.session_state:
    st.session_state.last_repo_url = None
# Pinecone chunk popup states
for i in range(1, 100):
    if f"show_chunk_{i}" not in st.session_state:
        st.session_state[f"show_chunk_{i}"] = False
    if f"show_pinecone_{i}" not in st.session_state:
        st.session_state[f"show_pinecone_{i}"] = False


# ============================================================================
# TABS
# ============================================================================
tab_chat, tab_graph, tab_tools = st.tabs(["Chat", "Knowledge Graph", "Tools"])

# ============================================================================
# TAB 1: CHAT
# ============================================================================
with tab_chat:
    # SIDEBAR
    with st.sidebar:
        st.header("Repository Indexing")
        
        repo_url = st.text_input(
            "GitHub Repository URL",
            placeholder="https://github.com/tiangolo/fastapi",
            key="repo_url_input"
        )
        
        st.subheader("Actions")
        
        col1, col2 = st.columns(2)
        with col1:
            start_index = st.button("Start Indexing", use_container_width=True, key="start_btn")
        with col2:
            refresh_status = st.button("Refresh", use_container_width=True, key="refresh_btn")
        
        st.divider()
        
        # âœ¨ VECTOR EMBEDDINGS SECTION
        # Hide embeddings section for MCP demo - students focus on agent orchestration
        with st.expander("⚙️ Vector Embeddings (Optional - Advanced)", expanded=False):
            st.info("💡 Embeddings add semantic search capability. For core MCP demo, Neo4j graph search is sufficient.")
            st.subheader("Vector Embeddings (Pinecone)")
            
            embed_button = st.button(
            "Embed Repository",
            use_container_width=True,
            key="embed_btn",
            help="Create 650-line code chunks and generate embeddings for semantic search"
        )
        
        if embed_button:
            if not repo_url:
                st.error("Please enter a repository URL first!")
            else:
                st.session_state.embedding_active = True
                st.session_state.last_repo_url = repo_url
                st.rerun()
        
        # Show embedding progress if active
        if st.session_state.get("embedding_active", False):
            st.markdown("### Embedding Progress")
            
            progress_placeholder = st.empty()
            status_container = st.container()
            
            try:
                # Get repository URL
                embed_url = st.session_state.get("last_repo_url", repo_url)
                
                if embed_url:
                    with progress_placeholder:
                        st.progress(25, text="Starting embedding process...")
                    
                    # Call embedding API
                    with status_container:
                        with st.spinner("Creating embeddings... This may take a few minutes"):
                            embed_res = requests.post(
                                f"{API_BASE}/api/embeddings/create",
                                json={
                                    "repo_url": embed_url,
                                    "chunk_size": 650
                                },
                                timeout=600  # 10 minute timeout
                            )
                    
                    if embed_res.ok:
                        embed_data = embed_res.json()
                        
                        # Check if successful or fallback
                        if embed_data.get('success') == False:
                            # Pinecone not configured - graceful fallback
                            with status_container:
                                st.warning(f"⚠️ {embed_data.get('message', 'Embeddings not available')}")
                                st.info(f"💡 Fallback: {embed_data.get('fallback', 'Neo4j graph search available')}")
                                st.caption(embed_data.get('note', ''))
                            
                            st.session_state.embedding_active = False
                            st.session_state.embeddings_created = False
                        
                        else:
                            # Successfully created embeddings
                            with progress_placeholder:
                                st.progress(100, text="Embedding Complete!")
                            
                            with status_container:
                                st.success("✅ Embeddings Created Successfully!")
                            
                                col1, col2 = st.columns(2)
                                with col1:
                                    st.metric(
                                        "Code Chunks",
                                        embed_data.get('chunks_created', 0)
                                    )
                                with col2:
                                    st.metric(
                                        "Vectors Stored",
                                        embed_data.get('vectors_upserted', embed_data.get('embeddings_generated', 0))
                                    )
                            
                                embed_stats = embed_data.get('stats', {})
                                st.info(f"""
                                **Embedding Details:**
                                - Repository: {embed_data.get('repo_id', 'unknown')}
                                - Chunks Created: {embed_data.get('chunks_created', 0)}
                                - Vectors Upserted: {embed_data.get('vectors_upserted', 0)}
                                - Embedding Dimension: {embed_stats.get('dimension', 384)}
                                - Metric: {embed_stats.get('metric', 'cosine')}
                                """)
                            
                            st.session_state.embedding_active = False
                            st.session_state.embeddings_created = True
                            time.sleep(3)
                        
                    else:
                        with status_container:
                            st.warning(f"⚠️ Embedding service unavailable: {embed_res.text}")
                            st.info("💡 Using Neo4j graph search instead (no semantic search)")
                        st.session_state.embedding_active = False
                        
            except requests.exceptions.Timeout:
                with status_container:
                    st.error("Embedding timeout - large repository may take longer")
                st.session_state.embedding_active = False
            except Exception as e:
                with status_container:
                    st.error(f"Error: {str(e)}")
                st.session_state.embedding_active = False
        
        # Show embedding status
        if st.session_state.get("embeddings_created", False):
            st.success("Embeddings Ready for Search!")
        
        if start_index and repo_url:
            st.session_state.indexing_active = True
            try:
                # Show progress modal instead of logger
                st.toast(f"🚀 Starting indexing: {repo_url}")
                
                res = requests.post(
                    f"{API_BASE}/api/index",
                    json={"repo_url": repo_url, "full_index": True},
                    timeout=10
                )
                if res.ok:
                    job_data = res.json()
                    st.session_state.current_job_id = job_data.get('job_id')
                    st.cache_data.clear()
                    st.rerun()
                else:
                    st.session_state.indexing_active = False
                    st.error(f"Error: {res.text}")
            except Exception as e:
                st.session_state.indexing_active = False
                st.error(f"Connection error: {str(e)}")
        
        # Ž­ MODAL OVERLAY: Show if indexing active
        if st.session_state.indexing_active and st.session_state.current_job_id:
            # CSS for modal overlay (subtle blur, no black overlay)
            st.markdown("""
            <style>
            .modal-overlay {
                position: fixed;
                top: 0;
                left: 0;
                width: 100%;
                height: 100%;
                background-color: transparent;
                display: flex;
                justify-content: center;
                align-items: center;
                z-index: 9999;
                backdrop-filter: blur(3px);
            }
            .modal-box {
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                padding: 60px 50px;
                border-radius: 15px;
                text-align: center;
                box-shadow: 0 10px 40px rgba(0, 0, 0, 0.4);
                max-width: 550px;
                color: white;
            }
            .modal-title {
                font-size: 32px;
                font-weight: bold;
                margin-bottom: 15px;
            }
            .modal-message {
                font-size: 18px;
                margin-bottom: 40px;
                opacity: 0.95;
            }
            .modal-warning {
                font-size: 14px;
                opacity: 0.85;
                background: rgba(0, 0, 0, 0.2);
                padding: 15px;
                border-radius: 8px;
                margin-top: 30px;
            }
            .spinner {
                display: inline-block;
                font-size: 48px;
                animation: spin 2s linear infinite;
                margin-bottom: 20px;
            }
            @keyframes spin {
                0% { transform: rotate(0deg); }
                100% { transform: rotate(360deg); }
            }
            </style>
            """, unsafe_allow_html=True)
            
            # Streaming progress loop
            job_id = st.session_state.current_job_id
            max_attempts = 300  # 5 minutes with 1 second polling
            attempt = 0
            
            # Create placeholders for streaming updates
            modal_container = st.container()
            
            while attempt < max_attempts:
                try:
                    # Poll job status
                    jobs_res = requests.get(f"{API_BASE}/api/index/jobs/{job_id}", timeout=10)
                    if jobs_res.ok:
                        job = jobs_res.json()
                        status = job.get("status")
                        progress = job.get("progress", 0)
                        files = job.get("files_processed", 0)
                        entities = job.get("entities_created", 0)
                        relationships = job.get("relationships_created", 0)
                        
                        # Update modal with streaming progress
                        with modal_container:
                            st.markdown("""
                            <div class="modal-overlay">
                                <div class="modal-box">
                                    <div class="spinner"></div>
                                    <div class="modal-title">Indexing Repository</div>
                                    <div class="modal-message">Processing your codebase...</div>
                            """, unsafe_allow_html=True)
                            
                            # Streaming progress bar
                            progress_val = min(progress / 100, 1.0)
                            st.progress(progress_val, text=f"Progress: {progress}%")
                            
                            # Live metrics (3 columns)
                            col1, col2, col3 = st.columns(3)
                            with col1:
                                st.metric("Files", files)
                            with col2:
                                st.metric("Entities", entities)
                            with col3:
                                st.metric("Relations", relationships)
                            
                            st.markdown("""
                                    <div class="modal-warning">
                                         <strong>This may take 1-2 minutes</strong><br>
                                        Please keep this tab open and do not refresh
                                    </div>
                                </div>
                            </div>
                            """, unsafe_allow_html=True)
                        
                        #  COMPLETED: Clear state and rerun
                        if status == "completed":
                            st.session_state.indexing_active = False
                            st.session_state.current_job_id = None
                            st.cache_data.clear()
                            time.sleep(1)
                            st.rerun()
                        
                        # âŒ FAILED: Show error
                        elif status == "failed":
                            st.session_state.indexing_active = False
                            st.error(f"Indexing failed: {job.get('error', 'Unknown error')}")
                            time.sleep(3)
                            st.rerun()
                        
                        # â³ PENDING/RUNNING: Keep polling
                        time.sleep(1)
                        attempt += 1
                    else:
                        break
                except Exception as e:
                    attempt += 1
                    time.sleep(1)
            
            # Timeout
            st.session_state.indexing_active = False
            st.error(" Indexing timeout. Please refresh.")
        
        if refresh_status:
            st.rerun()
        
        st.divider()
        
        #  Only show completed jobs summary (NOT active jobs)
        try:
            jobs_res = requests.get(f"{API_BASE}/api/index/jobs", timeout=10)
            if jobs_res.ok:
                all_jobs = jobs_res.json().get("jobs", [])
                completed_jobs = [j for j in all_jobs if j.get("status") == "completed"]
                
                if completed_jobs:
                    st.subheader(" Recently Indexed Repositories")
                    for job in completed_jobs[-3:]:  # Show last 3
                        col1, col2, col3, col4 = st.columns(4)
                        with col1:
                            st.metric("Packages", job.get("files_processed", 0))
                        with col2:
                            st.metric("Entities", job.get("entities_created", 0))
                        with col3:
                            st.metric("Relations", job.get("relationships_created", 0))
                        with col4:
                            st.metric("Status", " Done")
        except:
            pass  # Silent: no completed jobs to show
        
        # DATABASE STATS with State Management (NO CACHE - updates in real-time)
        # DATABASE STATS with State Management (NO CACHE - updates in real-time)
        st.subheader(" Neo4j Database Stats")
        try:
            res = requests.get(f"{API_BASE}/api/index/status", timeout=10)
            if res.ok:
                stats = res.json().get("statistics", {})
                nodes = stats.get("nodes", {})
                
                # Store stats in session state (persists across reruns during indexing)
                st.session_state.db_stats = {
                    "Package": nodes.get("Package", 0),
                    "File": nodes.get("File", 0),
                    "Class": nodes.get("Class", 0),
                    "Function": nodes.get("Function", 0),
                    "Parameter": nodes.get("Parameter", 0),
                    "Type": nodes.get("Type", 0),
                }
                
                col1, col2, col3 = st.columns(3)
                with col1:
                    st.metric("Packages", st.session_state.db_stats["Package"])
                    st.metric("Files", st.session_state.db_stats["File"])
                with col2:
                    st.metric("Classes", st.session_state.db_stats["Class"])
                    st.metric("Functions", st.session_state.db_stats["Function"])
                with col3:
                    st.metric("Parameters", st.session_state.db_stats["Parameter"])
                    st.metric("Types", st.session_state.db_stats["Type"])
        except:
            st.warning("Could not fetch Neo4j stats")
        
        st.divider()
        
        # PINECONE EMBEDDINGS STATS
        st.subheader("⚡ Vector Embeddings (Pinecone)")
        
        try:
            pinecone_res = requests.get(f"{API_BASE}/api/embeddings/stats", timeout=10)
            if pinecone_res.ok:
                pinecone_data = pinecone_res.json()
                
                if pinecone_data.get("status") == "unavailable":
                    st.warning(f"⚠️ {pinecone_data.get('message', 'Pinecone not configured')}")
                    st.info(f"💡 {pinecone_data.get('fallback', 'Using Neo4j graph search')}")
                    st.caption("**Setup:** Set PINECONE_API_KEY and COHERE_API_KEY environment variables to enable semantic search")
                
                elif pinecone_data.get("status") == "available":
                    summary = pinecone_data.get("summary", {})
                    stats = pinecone_data.get("stats", {})
                    
                    # Status indicator
                    status_icon = "✅" if summary.get("chunks_total", 0) > 0 else "⏳"
                    st.write(f"{status_icon} **Status:** {summary.get('status', 'Unknown')}")
                    
                    # Metrics
                    col1, col2 = st.columns(2)
                    with col1:
                        st.metric(
                            "📦 Code Chunks",
                            summary.get("chunks_total", 0)
                        )
                        st.caption(f"Model: {summary.get('embedding_model', 'N/A')}")
                    
                    with col2:
                        st.metric(
                            "🔄 Reranker",
                            summary.get('reranker', 'N/A').split('(')[0]
                        )
                        st.caption(f"Index: {stats.get('index_name', 'N/A')}")
                    
                    # Detailed stats in expander
                    with st.expander("📊 Detailed Stats"):
                        st.write(f"**Total Vectors:** {stats.get('total_vectors', 0)}")
                        st.write(f"**Dimension:** {stats.get('dimension', 0)}")
                        st.write(f"**Metric:** {stats.get('metric', 'cosine')}")
                        
                        if stats.get('namespaces'):
                            st.write("**Namespaces:**")
                            for ns_name, ns_stats in stats.get('namespaces', {}).items():
                                st.write(f"  • {ns_name}: {ns_stats.get('vector_count', 0)} vectors")
                
                elif pinecone_data.get("status") == "unavailable":
                    st.warning(f"⚠️ {pinecone_data.get('message', 'Pinecone not configured')}")
                    st.info(f"💡 {pinecone_data.get('fallback', 'Using Neo4j graph search')}")
                
                else:
                    st.error(f"❌ {pinecone_data.get('error', 'Error fetching Pinecone stats')}")
                    st.info("💡 Neo4j graph search still available")
        
        except requests.exceptions.Timeout:
            st.warning("⏱️ Pinecone stats timeout")
        except Exception as e:
            st.warning(f"⚠️ Could not fetch Pinecone stats: {str(e)[:50]}")
            st.caption("💡 Neo4j graph search available as fallback")
        
        st.divider()
        
        # DATABASE VERIFICATION
        with st.expander(" Verify Database", expanded=False):
            col1, col2 = st.columns(2)
            
            with col1:
                if st.button("Check DB Stats"):
                    try:
                        response = requests.get(f"{API_BASE}/health", timeout=5)
                        if response.ok:
                            health = response.json()
                            neo4j_stats = health.get("components", {}).get("neo4j", {}).get("statistics", {})
                            
                            st.write("**Database Stats:**")
                            nodes = neo4j_stats.get("nodes", {})
                            rels = neo4j_stats.get("relationships", {})
                            
                            node_col, rel_col = st.columns(2)
                            with node_col:
                                st.write("**Nodes:**")
                                for node_type, count in sorted(nodes.items()):
                                    st.write(f"   {node_type}: {count}")
                            
                            with rel_col:
                                st.write("**Relationships:**")
                                for rel_type, count in sorted(rels.items()):
                                    st.write(f"   {rel_type}: {count}")
                    except Exception as e:
                        st.error(f"Error: {str(e)}")
    
    # MAIN CHAT AREA
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
                    # AGENTIC AI MESSAGE
                    if "thinking_process" in msg:
                        thinking_steps = msg.get("thinking_process", [])
                        tools_used = msg.get("tools_used", [])
                        iterations = msg.get("iterations", 0)
                        retrieved_context = msg.get("retrieved_context", [])
                        
                        st.divider()
                        
                        with st.expander(f"🧠 Thinking Process ({iterations} iterations)", expanded=False):
                            for i, step in enumerate(thinking_steps, 1):
                                st.caption(f"**Step {i}:** {step[:300]}...")
                        
                        # SHOW RETRIEVED CONTEXT FROM AGENTIC SEARCH
                        if retrieved_context:
                            embeddings_sources = [s for s in retrieved_context if s.get('source_type') == 'pinecone' or s.get('type') == 'code_chunk']
                            neo4j_sources = [s for s in retrieved_context if s.get('source_type') == 'neo4j' or s.get('type') == 'relationship']
                            
                            if embeddings_sources:
                                st.write("**📝 Pinecone Code Chunks (Semantic Search)**")
                                for j, source in enumerate(embeddings_sources, 1):
                                    with st.container(border=True):
                                        col1, col2 = st.columns([0.85, 0.15])
                                        
                                        with col1:
                                            st.markdown(f"""
**{source.get('file_name', 'unknown')}** | {source.get('language', 'python')}
- **Lines:** {source.get('lines', 'N/A')}
- **Relevance:** {source.get('relevance', 'N/A')}
- **Start:** {source.get('start_line', 'N/A')} | **End:** {source.get('end_line', 'N/A')}
                                            """)
                                        
                                        with col2:
                                            if st.button("📂 View", key=f"agentic_history_view_{j}"):
                                                st.session_state[f"show_agentic_history_{j}"] = True
                                    
                                    if st.session_state.get(f"show_agentic_history_{j}"):
                                        st.code(source.get('content', 'N/A'), language=source.get('language', 'python'))
                            
                            if neo4j_sources:
                                st.write("**🔗 Neo4j Entity Relationships (Graph)**")
                                for k, source in enumerate(neo4j_sources, 1):
                                    with st.container(border=True):
                                        st.markdown(f"""
**{source.get('entity_type', 'Unknown')}:** `{source.get('entity', 'unknown')}`
- **Dependencies:** {', '.join(source.get('dependencies', [])[:3]) or 'None'}
- **Used by:** {', '.join(source.get('used_by', [])[:3]) or 'Not directly used'}
- **Module:** {source.get('module', 'N/A')}
                                        """)
                        
                        if tools_used:
                            st.write("**🔧 Tools Used:**")
                            tool_str = " ".join([f'<span class="agent-badge">{t}</span>' for t in tools_used])
                            st.markdown(tool_str, unsafe_allow_html=True)
                    
                    # RAG MESSAGE
                    else:
                        sources = msg.get("sources", [])
                        agents = msg.get("agents", [])
                        
                        if sources:
                            # Separate pinecone and neo4j sources
                            pinecone_sources = [s for s in sources if s.get('source_type') == 'pinecone' or s.get('type') == 'code_chunk']
                            neo4j_sources = [s for s in sources if s.get('source_type') == 'neo4j' or s.get('type') == 'relationship']
                            
                            # PINECONE CHUNKS
                            if pinecone_sources:
                                st.write("**📝 Pinecone Code Chunks (Semantic Search)**")
                                for j, source in enumerate(pinecone_sources, 1):
                                    with st.container(border=True):
                                        col1, col2 = st.columns([0.85, 0.15])
                                        
                                        with col1:
                                            # Build citation text, omitting N/A and None values
                                            citation_parts = [f"**{source.get('file_name', 'unknown')}** | {source.get('language', 'python')}"]

                                            if source.get('lines') and source.get('lines') != 'N/A':
                                                citation_parts.append(f"Lines {source.get('lines')}")

                                            if source.get('relevance_percent') and source.get('relevance_percent') != 'N/A':
                                                citation_parts.append(f"Relevance: {source.get('relevance_percent')}")

                                            if source.get('reranked') is not None:
                                                citation_parts.append(f"Reranked: {'✅ Yes' if source.get('reranked') else '❌ No'}")

                                            if source.get('start_line') and source.get('start_line') != 'N/A':
                                                citation_parts.append(f"Line {source.get('start_line')}-{source.get('end_line', 'N/A')}")

                                            if source.get('preview') and source.get('preview') != 'N/A':
                                                preview = source.get('preview')[:80] + "..." if len(source.get('preview', '')) > 80 else source.get('preview')
                                                citation_parts.append(f"Preview: {preview}")

                                            st.markdown(" | ".join(citation_parts))
                                        
                                        with col2:
                                            if st.button("📂 View Code", key=f"pinecone_view_{j}", use_container_width=True):
                                                st.session_state[f"show_pinecone_{j}"] = True
                                    
                                    # Pinecone code popup modal
                                    if st.session_state.get(f"show_pinecone_{j}"):
                                        st.markdown("---")
                                        col_code, col_close = st.columns([0.95, 0.05])
                                        with col_code:
                                            st.write(f"**📄 {source.get('file_name', 'unknown')}** (Lines {source.get('lines', 'N/A')})")
                                        with col_close:
                                            if st.button("✕", key=f"pinecone_close_{j}"):
                                                st.session_state[f"show_pinecone_{j}"] = False
                                        
                                        st.code(source.get('content', source.get('preview', 'Content not available')), language=source.get('language', 'python'))
                                        st.markdown("---")
                            
                            # NEO4J RELATIONSHIPS
                            if neo4j_sources:
                                st.write("**🔗 Neo4j Entity Relationships (Graph)**")
                                for k, source in enumerate(neo4j_sources, 1):
                                    with st.container(border=True):
                                        # Build Neo4j citation, omitting empty/N/A values
                                        neo4j_lines = [f"**{source.get('entity_type', 'Unknown')}**: {source.get('entity', 'unknown')}"]

                                        deps = source.get('dependencies', [])
                                        if deps and deps != ['None'] and all(d != 'None' and d != 'N/A' for d in deps):
                                            neo4j_lines.append(f"- Dependencies: {', '.join(deps[:3])}")

                                        used_by = source.get('used_by', [])
                                        if used_by and used_by != ['Not used'] and all(u != 'Not used' and u != 'N/A' for u in used_by):
                                            neo4j_lines.append(f"- Used by: {', '.join(used_by[:3])}")

                                        if source.get('module') and source.get('module') != 'N/A':
                                            neo4j_lines.append(f"- Module: {source.get('module')}")

                                        if source.get('node_type') and source.get('node_type') != 'N/A':
                                            neo4j_lines.append(f"- Type: {source.get('node_type')}")

                                        st.markdown("\n".join(neo4j_lines))
                        
                        if agents:
                            agent_str = " ".join([f'<span class="agent-badge">{a}</span>' for a in agents])
                            st.markdown(agent_str, unsafe_allow_html=True)
    
    st.divider()
    
    # CHAT INPUT
    query = st.chat_input("Ask about the codebase...")
    
    if query:
        with st.chat_message("user"):
            st.write(query)
        
        st.session_state.messages.append({"role": "user", "content": query})
        
        try:
            with st.chat_message("assistant"):
                # DETERMINE WHICH ENDPOINT TO USE
                if chat_mode == "Agentic AI":
                    # ===== AGENTIC AI MODE =====
                    with st.spinner("🧠 GPT-4 is reasoning and chaining tools..."):
                        payload = {"query": query, "session_id": st.session_state.session_id or "streamlit-demo"}
                        
                        res = requests.post(
                            f"{API_BASE}/api/agentic-chat",
                            json=payload,
                            timeout=120  # Agentic can take longer
                        )
                    
                    if res.ok:
                        data = res.json()
                        answer = data["response"]
                        thinking_process = data.get("thinking_process", [])
                        tools_used = data.get("tools_used", [])
                        iterations = data.get("iterations", 0)
                        retrieved_context = data.get("retrieved_context", [])

                        # Display answer with streaming effect
                        message_placeholder = st.empty()
                        displayed_text = ""
                        for char in answer:
                            displayed_text += char
                            message_placeholder.write(displayed_text)
                            time.sleep(0.01)
                        
                        st.divider()
                        
                        # SHOW AGENTIC THINKING PROCESS
                        with st.expander(f"🧠 Thinking Process ({iterations} iterations)", expanded=True):
                            for i, step in enumerate(thinking_process, 1):
                                st.caption(f"**Step {i}:** {step[:200]}...")
                        
                        # SHOW RETRIEVED CONTEXT (SOURCES)
                        if retrieved_context:
                            embeddings_sources = [s for s in retrieved_context if s.get('source_type') == 'pinecone' or s.get('type') == 'code_chunk']
                            neo4j_sources = [s for s in retrieved_context if s.get('source_type') == 'neo4j' or s.get('type') == 'relationship']
                            
                            if embeddings_sources:
                                st.write("### 📝 Pinecone Code Chunks (Semantic Search)")
                                for idx, source in enumerate(embeddings_sources, 1):
                                    with st.container(border=True):
                                        col1, col2 = st.columns([0.8, 0.2])
                                        
                                        with col1:
                                            st.markdown(f"""
**{source.get('file_name', 'unknown')}** | {source.get('language', 'python')}
- **Lines:** {source.get('lines', 'N/A')}
- **Relevance:** {source.get('relevance', 'N/A')}
- **Start:** {source.get('start_line', 'N/A')} | **End:** {source.get('end_line', 'N/A')}
                                            """)
                                            st.caption(f"Preview: {source.get('preview', 'N/A')[:100]}...")
                                        
                                        with col2:
                                            view_key = f"agentic_view_{idx}_{time.time()}"
                                            if st.button("📂 View Code", key=view_key):
                                                st.session_state[f"show_{view_key}"] = True
                                            
                                            if st.session_state.get(f"show_{view_key}"):
                                                st.code(source.get('content', source.get('preview', 'N/A')), language=source.get('language', 'python'))
                            
                            if neo4j_sources:
                                st.write("### 🔗 Neo4j Entity Relationships (Graph)")
                                for idx, source in enumerate(neo4j_sources, 1):
                                    with st.container(border=True):
                                        st.markdown(f"""
**{source.get('entity_type', 'Unknown')}:** `{source.get('entity', 'unknown')}`
- **Dependencies:** {', '.join(source.get('dependencies', [])[:3]) or 'None'}
- **Used by:** {', '.join(source.get('used_by', [])[:3]) or 'Not directly used'}
- **Module:** {source.get('module', 'N/A')}
                                        """)
                        
                        # SHOW TOOLS USED
                        if tools_used:
                            st.write("**🔧 Tools Used:**")
                            tool_str = " ".join([f'<span class="agent-badge">{t}</span>' for t in tools_used])
                            st.markdown(tool_str, unsafe_allow_html=True)
                        
                        st.session_state.messages.append({
                            "role": "assistant",
                            "content": answer,
                            "thinking_process": thinking_process,
                            "tools_used": tools_used,
                            "iterations": iterations,
                            "retrieved_context": retrieved_context
                        })
                        st.rerun()
                    else:
                        st.error(f"Error: {res.text}")
                
                else:
                    # ===== RAG MODE (Original) =====
                    payload = {"query": query, "session_id": st.session_state.session_id}
                    
                    with st.spinner("Processing..."):
                        res = requests.post(
                            f"{API_BASE}/api/rag-chat",
                            json=payload,
                            timeout=60
                        )
                    
                    if res.ok:
                        data = res.json()
                        st.session_state.session_id = data["session_id"]
                        
                        answer = data["response"]
                        retrieved_context = data.get("retrieved_context", [])
                        agents_used = data.get("agents_used", [])
                        
                        # Streaming effect
                        message_placeholder = st.empty()
                        displayed_text = ""
                        for char in answer:
                            displayed_text += char
                            message_placeholder.write(displayed_text)
                            time.sleep(0.01)
                        
                        st.divider()
                        
                        if retrieved_context:
                            embeddings_sources = [s for s in retrieved_context if s.get('type') == 'code_chunk']
                            graph_sources = [s for s in retrieved_context if s.get('type') == 'relationship']
                            
                            if embeddings_sources:
                                st.write("### 📝 Pinecone Code Chunks (Semantic Search)")
                                for idx, source in enumerate(embeddings_sources, 1):
                                    with st.container(border=True):
                                        col1, col2 = st.columns([0.8, 0.2])
                                        
                                        with col1:
                                            reranked_status = "✅ Reranked" if source.get('reranked') else "⭕ Original"
                                            st.markdown(f"""
**{source.get('file_name', 'unknown')}** | {source.get('language', 'python')}
- **Lines:** {source.get('lines', 'N/A')}
- **Relevance:** {source.get('relevance_percent', 'N/A')}
- **Status:** {reranked_status}
- **Chunk ID:** `{source.get('chunk_id', 'N/A')}`
- **Start:** {source.get('start_line', 'N/A')} | **End:** {source.get('end_line', 'N/A')}
- **Model:** {source.get('embedding_model', 'N/A')}
                                            """)
                                            st.caption(f"Preview: {source.get('preview', 'N/A')[:100]}...")
                                        
                                        with col2:
                                            view_key = f"view_{st.session_state.session_id}_{idx}_{time.time()}"

                                            if st.button("📂 View Code", key=view_key):
                                                st.session_state[f"show_{view_key}"] = True

                                            # Show code if button clicked
                                            if st.session_state.get(f"show_{view_key}"):
                                                st.code(source.get('content'), language="python")
                                        st.divider()
                                        col_title, col_x = st.columns([0.9, 0.1])
                                        with col_title:
                                            st.subheader(f"📄 {source.get('file_name', 'unknown')} (Lines {source.get('lines', 'N/A')})")
                                        with col_x:
                                            if st.button("✕", key=f"chunk_close_{idx}"):
                                                st.session_state[f"show_chunk_{idx}"] = False
                                        
                                        st.code(source.get('content', source.get('preview', 'Code not available')), language=source.get('language', 'python'))
                                        st.divider()
                            
                            if graph_sources:
                                st.write("### 🔗 Neo4j Entity Relationships (Graph)")
                                for idx, source in enumerate(graph_sources, 1):
                                    with st.container(border=True):
                                        st.markdown(f"""
**{source.get('entity_type', 'Unknown')}:** `{source.get('entity', 'unknown')}`
- **Dependencies:** {', '.join(source.get('dependencies', [])[:3]) or 'None'}
- **Used by:** {', '.join(source.get('used_by', [])[:3]) or 'Not directly used'}
- **Module:** {source.get('module', 'N/A')}
- **Line:** {source.get('line_number', 'N/A')}
                                        """)
                        
                        if agents_used:
                            agent_str = " ".join([f'<span class="agent-badge">{a}</span>' for a in agents_used])
                            st.markdown(agent_str, unsafe_allow_html=True)
                        
                        st.session_state.messages.append({
                            "role": "assistant",
                            "content": answer,
                            "sources": retrieved_context,
                            "agents": agents_used
                        })
                        st.rerun()
                    else:
                        st.error(f"Error: {res.text}")
        
        except requests.exceptions.Timeout:
            st.error(" Timeout")
        except Exception as e:
            st.error(f"Error: {str(e)}")


# ============================================================================
# TAB 2: KNOWLEDGE GRAPH
# ============================================================================
with tab_graph:
    st.header("Knowledge Graph Visualization")
    
    st.subheader("Select Node Type at Specific Node")
    
    def get_all_entities():
        """Fetch all entities grouped by type - includes Functions, Methods, Parameters, etc."""
        try:
            # Query ALL node types (Class, Function, Method, Parameter, Type, Package, File, Docstring)
            cypher = """
            MATCH (e)
            WHERE e.name IS NOT NULL
            WITH labels(e)[0] as node_type, e.name as name
            RETURN node_type, name
            ORDER BY node_type, name
            LIMIT 5000
            """
            response = requests.post(
                f"{API_BASE}/api/query/execute",
                json={"query": cypher},
                timeout=10
            )
            if response.ok:
                results = response.json().get("result", [])
                entities_dict = {}
                for r in results:
                    node_type = r.get("node_type", "Unknown")
                    name = r.get("name", "")
                    
                    # Skip empty names
                    if not name:
                        continue
                    
                    # For Functions + Methods: combine into "Function/Method"
                    if node_type == "Method":
                        display_type = "Function/Method"
                    else:
                        display_type = node_type
                    
                    if display_type not in entities_dict:
                        entities_dict[display_type] = []
                    entities_dict[display_type].append(name)
                
                # Remove duplicates and sort
                for key in entities_dict:
                    entities_dict[key] = sorted(set(entities_dict[key]))
                
                return entities_dict
        except Exception as e:
            st.error(f"Error fetching entities: {str(e)}")
        return {}
    
    entities_by_type = get_all_entities()
    
    if not entities_by_type:
        st.warning("No entities found. Index a repository first.")
    else:
        # DUAL DROPDOWNS: Node Type â†’ Specific Nodes with SEARCH
        col1, col2, col3 = st.columns([2, 2, 1])
        
        with col1:
            selected_type = st.selectbox(
                "1 Node Type",
                options=["Select a type..."] + sorted(list(entities_by_type.keys())),
                key="type_select"
            )
        
        with col2:
            if selected_type and selected_type != "Select a type...":
                entity_list = entities_by_type.get(selected_type, [])
                
                # ” Add search bar for filtering large lists
                search_term = st.text_input(
                    f"Search {selected_type}s ({len(entity_list)} available)",
                    placeholder="Type to filter...",
                    key="entity_search"
                )
                
                # Filter list based on search
                if search_term:
                    filtered_list = [e for e in entity_list if search_term.lower() in e.lower()]
                else:
                    filtered_list = entity_list
                
                if filtered_list:
                    entity_name = st.selectbox(
                        f"2 Select {selected_type}",
                        options=filtered_list,
                        key="entity_select"
                    )
                else:
                    st.warning(f"No {selected_type} found matching '{search_term}'")
                    entity_name = None
            else:
                st.selectbox(
                    "2 Select type first",
                    options=["No type selected"],
                    disabled=True,
                    key="entity_select_disabled"
                )
                entity_name = None
        
        with col3:
            visualize_button = st.button("Visualize", use_container_width=True, disabled=(entity_name is None))
        
        if visualize_button and entity_name:
            # ¤– AI-POWERED VISUALIZATION PIPELINE WITH MULTIPLE CYPHER QUERIES
            with st.spinner(f"Step 1: Generating optimized Cypher queries for {selected_type}..."):
                try:
                    # STEP 1: Generate MULTIPLE Cypher queries based on node type and relationships
                    cypher_queries = get_cypher_query_templates(selected_type, entity_name)
                    
                    st.info(f" Generated {len(cypher_queries)} optimized Cypher queries")
                    st.caption(f" {get_query_description(selected_type)}")
                    
                except Exception as e:
                    st.error(f"Step 1 failed: {str(e)}")
                    st.stop()
            
            # Display the generated queries in an expander
            # Display the generated queries in an expander
            with st.expander(f"🔍 Generated Cypher Queries for {entity_name}", expanded=False):
                for i, q in enumerate(cypher_queries, 1):
                    st.code(q, language="cypher")
            
            # STEP 2: Execute ALL Cypher queries and collect results
            all_results = []
            query_status_list = []
            
            with st.spinner(f"Step 2: Executing {len(cypher_queries)} queries on Neo4j..."):
                try:
                    progress_bar = st.progress(0)
                    
                    for idx, query in enumerate(cypher_queries, 1):
                        try:
                            cypher_exec_response = requests.post(
                                f"{API_BASE}/api/query/execute",
                                json={
                                    "query": query,
                                    "params": {"name": entity_name}
                                },
                                timeout=20
                            )
                            
                            if cypher_exec_response.ok:
                                exec_data = cypher_exec_response.json()
                                results = exec_data.get("result", [])
                                all_results.extend(results)
                                query_status_list.append({
                                    "Query": idx,
                                    "Status": " Success",
                                    "Results": len(results)
                                })
                            else:
                                query_status_list.append({
                                    "Query": idx,
                                    "Status": " Failed",
                                    "Results": 0
                                })
                        except Exception as q_error:
                            query_status_list.append({
                                "Query": idx,
                                "Status": " Error",
                                "Results": 0
                            })
                        
                        # Update progress
                        progress_bar.progress(idx / len(cypher_queries))
                    
                    progress_bar.empty()
                    
                    if not all_results:
                        st.warning(f"No relationships found for {entity_name}")
                        # Show query status for debugging
                        import pandas as pd
                        status_df = pd.DataFrame(query_status_list)
                        st.dataframe(status_df, use_container_width=True)
                        st.stop()
                    
                    st.success(f" All {len(cypher_queries)} queries executed - {len(all_results)} total results")
                    
                   # Show query status summary (text only, no dataframe)
                    with st.expander(" Query Execution Status"):
                        for status in query_status_list:
                            query_num = status.get("Query", "?")
                            status_icon = "✅" if status.get("Status") == " Success" else "❌"
                            results = status.get("Results", 0)
                            st.write(f"{status_icon} Query {query_num}: {results} results")
                    
                except Exception as e:
                    st.error(f"Step 2 failed: {str(e)}")
                    st.stop()
            

            # STEP 2.5: Display query results in a table
            with st.expander(f"📊 All Query Results ({len(all_results)} results)", expanded=False):
                if all_results:
                    # Display as JSON instead of dataframe (avoids pyarrow issues)
                    st.json(all_results[:5])  # Show first 5 results
                    if len(all_results) > 5:
                        st.caption(f"... and {len(all_results) - 5} more results")
                else:
                    st.warning("No results to display")
            
            
            # STEP 3: Render interactive network graph
            # STEP 3: RENDER USING MERMAID INSTEAD
            st.divider()

            with st.spinner(f"⏳ Step 3: Generating Mermaid diagram..."):
                try:
                    # Call your existing mermaid endpoint
                    mermaid_response = requests.post(
                        f"{API_BASE}/api/graph/generate-mermaid",
                        json={"query_results": all_results},
                        params={"entity_name": entity_name, "entity_type": selected_type},
                        timeout=60
                    )
                    
                    if mermaid_response.ok:
                        mermaid_data = mermaid_response.json()
                        mermaid_code = mermaid_data.get("mermaid_code", "")
                        
                        if mermaid_code and mermaid_code.strip():
                            st.success("✅ Diagram generated!")
                            st.divider()
                            
                            # Render with proper error handling
                            try:
                                render_mermaid_diagram(mermaid_code, height=600, diagram_title=f"📊 {entity_name} Relationships")
                            except Exception as render_err:
                                st.warning(f"Mermaid rendering issue: {str(render_err)[:100]}")
                                st.info("**Mermaid Code (for debugging):**")
                                st.code(mermaid_code, language="mermaid")
                        else:
                            st.warning("No diagram code generated")
                            st.info(f"Query returned {len(all_results)} results but no relationships found for diagram")
                    else:
                        st.error(f"Mermaid generation failed: {mermaid_response.text}")
                except Exception as e:
                    st.error(f"❌ Failed: {str(e)}")

# ============================================================================
# TAB 3: TOOLS
# ============================================================================
with tab_tools:
    st.title("Tools & Utilities")
    
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("System Health")
        try:
            health_res = requests.get(f"{API_BASE}/health", timeout=5)
            if health_res.ok:
                health_data = health_res.json()
                status = health_data.get("status", "unknown")
                
                if status == "healthy":
                    st.success(" System Healthy")
                else:
                    st.error("System Unhealthy")
                
                components = health_data.get("components", {})
                for comp_name, comp_data in components.items():
                    comp_status = comp_data.get("status", "unknown")
                    icon = "" if comp_status == "healthy" else "âŒ"
                    st.write(f"{icon} {comp_name.replace('_', ' ').title()}")
        except Exception as e:
            st.error(f"Error: {str(e)}")
    
    with col2:
        st.subheader("Database Management")
        st.warning("⚠️ This will delete ALL indexed data!")
        
        if st.checkbox("I understand", key="confirm_clear"):
            if st.button("🗑️ Clear Database"):
                try:
                    res = requests.post(
                        f"{API_BASE}/api/query/execute",
                        json={"query": "MATCH (n) DETACH DELETE n", "params": {}},
                        timeout=30
                    )
                    if res.ok:
                        st.success("✅ Database cleared!")
                        st.balloons()
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
                            f"{API_BASE}/api/embeddings/delete",
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
                stats_res = requests.get(f"{API_BASE}/api/embeddings/stats", timeout=10)
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
    st.write(f"**Base URL:** `{API_BASE}`")
    st.write(f"**Session:** `{st.session_state.session_id or 'Not initialized'}`")
    
    if st.button("View Endpoints"):
        endpoints = {
            "/health": "Health check",
            "/agents": "List agents",
            "/api/rag-chat": "RAG chat",
            "/api/graph/generate-mermaid": "Generate diagram",
            "/api/index": "Start indexing",
            "/api/query/find": "Find entity",
        }
        st.json(endpoints)