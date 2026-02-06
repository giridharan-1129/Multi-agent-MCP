import streamlit as st
import requests
import time
import os
import sys

sys.path.insert(0, '/mnt/project')

from mermaid_renderer import render_mermaid_diagram
from relationship_mappings import get_cypher_query_templates, get_query_description

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

if "indexing_active" not in st.session_state:
    st.session_state.indexing_active = False
if "embedding_active" not in st.session_state:
    st.session_state.embedding_active = False
if "embeddings_created" not in st.session_state:
    st.session_state.embeddings_created = False
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
# TABS
# ============================================================================
tab_chat, tab_graph, tab_tools = st.tabs(["Chat", "Knowledge Graph", "Tools"])

# ============================================================================
# TAB 1: CHAT
# ============================================================================
with tab_chat:
    # SIDEBAR
    with st.sidebar:
        st.header("🔍 Repository Indexing")
    
        # URL Input
        repo_url = st.text_input(
            "GitHub Repository URL",
            placeholder="https://github.com/tiangolo/fastapi",
            key="repo_url_input"
        )
    
        st.divider()
    
        # Action Buttons
        col1, col2 = st.columns(2)
        with col1:
            start_index = st.button("📦 Start Indexing", use_container_width=True, key="start_btn")
        with col2:
            start_embed = st.button("⚡ Start Embedding", use_container_width=True, key="embed_btn")
        
    # Handle Indexing Button
    if start_index:
        if not repo_url:
            st.error("Please enter a repository URL first!")
        else:
            st.session_state.indexing_active = True
            st.session_state.last_repo_url = repo_url
            st.rerun()
    
    # Handle Embedding Button
    if start_embed:
        if not repo_url:
            st.error("Please enter a repository URL first!")
        else:
            st.session_state.embedding_active = True
            st.session_state.last_repo_url = repo_url
            st.rerun()
    
    st.divider()
with st.sidebar:
    # Neo4j Stats
    st.subheader("📊 Neo4j Stats")
    
    col_stats, col_refresh = st.columns([3, 1])
    with col_refresh:
        if st.button("🔄", key="refresh_neo4j_btn", help="Refresh Neo4j stats"):
            st.session_state.neo4j_stats = None
            st.session_state.neo4j_stats_timestamp = None
    
    # Fetch stats if not cached
    if st.session_state.neo4j_stats and "error" not in st.session_state.neo4j_stats:
        try:
            res = requests.get(
                f"{GATEWAY_URL}/api/stats/neo4j",
                timeout=10
            )
            if res.ok:
                data = res.json()
                if data.get("success"):
                    st.session_state.neo4j_stats = data.get("data", {})
                    import time
                    st.session_state.neo4j_stats_timestamp = time.time()
                else:
                    st.session_state.neo4j_stats = {"error": data.get("error", "Unknown error")}
            else:
                st.session_state.neo4j_stats = {"error": "Request failed"}
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
            st.metric("Files", st.session_state.neo4j_stats.get("files", 0))
        st.caption(f"Total: {st.session_state.neo4j_stats.get('total_nodes', 0)} nodes")
    else:
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("Classes", "N/A")
        with col2:
            st.metric("Functions", "N/A")
        with col3:
            st.metric("Files", "N/A")
        if st.session_state.neo4j_stats and "error" in st.session_state.neo4j_stats:
            st.caption(f"Error: {st.session_state.neo4j_stats['error']}")
    
    st.divider()

    # Pinecone Stats
    st.subheader("⚡ Pinecone Embeddings")

    col_stats, col_refresh = st.columns([3, 1])
    with col_refresh:
        if st.button("🔄", key="refresh_pinecone_btn", help="Refresh Pinecone stats"):
            st.session_state.pinecone_stats = None
            st.session_state.pinecone_stats_timestamp = None

    # Fetch stats if not cached
    if st.session_state.pinecone_stats is None:
        try:
            res = requests.get(
                f"{GATEWAY_URL}/api/stats/pinecone",
                timeout=10
            )
            if res.ok:
                data = res.json()
                if data.get("success"):
                    st.session_state.pinecone_stats = data.get("data", {})
                    import time
                    st.session_state.pinecone_stats_timestamp = time.time()
                else:
                    st.session_state.pinecone_stats = {"error": data.get("message", "Pinecone unavailable")}
            else:
                st.session_state.pinecone_stats = {"error": "Request failed"}
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
                            with st.container(border=True):
                                col1, col2 = st.columns([0.8, 0.2])
                                
                                with col1:
                                    st.markdown(f"""
                                                    **{j}. {source.get('file_name', 'unknown')}**s
                                                    - **Language:** {source.get('language', 'python')}
                                                    - **Lines:** {source.get('start_line', '?')}-{source.get('end_line', '?')}
                                                    - **Relevance:** {round(source.get('relevance_score', 0) * 100)}% {'(reranked)' if source.get('reranked') else ''}
                                                                                            """)
                                    
                                with col2:
                                    if st.button("📂 View", key=f"history_source_{j}"):
                                        st.session_state[f"show_history_source_{j}"] = True
                                
                            if st.session_state.get(f"show_history_source_{j}"):
                                st.code(source.get('content', 'No content'), language=source.get('language', 'python'))
                                    
                    if neo4j_sources:  # ← CORRECT: Now at proper indentation level
                        st.write("**🔗 Neo4j Entities**")
                        for k, source in enumerate(neo4j_sources, 1):
                            with st.container(border=True):
                                st.markdown(f"""
                                                    **{source.get('entity_type', 'Unknown')}:** `{source.get('entity_name', 'unknown')}`
                                                    - **Module:** {source.get('module', 'N/A')}
                                                    - **Line:** {source.get('line_number', 'N/A')}
                                                                                        """)
                                                            
                    if tools_used:
                        st.write("**🔧 Tools Used:**")
                        tool_str = " ".join([f'<span class="agent-badge">{t}</span>' for t in tools_used])
                        st.markdown(tool_str, unsafe_allow_html=True)

st.divider()

# CHAT INPUT
query = st.chat_input("Ask about the codebase...")

if query:
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
                                    
                                    with col_expand:
                                        if st.button("📖", key=f"neo4j_view_{idx}", help="View details"):
                                            st.session_state[f"show_neo4j_{idx}"] = True
                                    
                                    if st.session_state.get(f"show_neo4j_{idx}"):
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
                                                - **Language:** {language}
                                                                            """)
                                                                        
                                    with col_score:
                                        relevance = chunk.get("relevance_score", 0)
                                        confidence = chunk.get("confidence", 0)
                                        reranked_badge = "✅" if chunk.get("reranked") else "📊"
                                        
                                        st.metric("Relevance", f"{relevance:.2f}", label_visibility="collapsed")
                                        st.metric("Confidence", f"{confidence:.2f}", label_visibility="collapsed")
                                        st.caption(f"{reranked_badge} {chunk.get('lines', 'N/A')}")
                                    
                                    with col_expand:
                                        if st.button("💻", key=f"pinecone_view_{idx}", help="View code"):
                                            st.session_state[f"show_pinecone_{idx}"] = True
                                    
                                    if st.session_state.get(f"show_pinecone_{idx}"):
                                        code_content = chunk.get("content") or chunk.get("preview", "")
                                        if code_content:
                                            st.code(code_content, language=language)
                                        else:
                                            st.info("No code content available")
                        
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
                f"{GATEWAY_URL}/api/chat",
                json={"query": f"Execute this Cypher query: {cypher}"},
                timeout=10
            )
            if response.ok:
                data = response.json()
                results = data.get("data", {}).get("query_results", []) if data.get("success") else []
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
                                f"{GATEWAY_URL}/api/chat",
                                json={
                                    "query": f"Execute Cypher query for {entity_name}: {query}"
                                },
                                timeout=20
                            )
                            if cypher_exec_response.ok:
                                exec_data = cypher_exec_response.json()
                                results = exec_data.get("data", {}).get("query_results", []) if exec_data.get("success") else []
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
            
            
            # STEP 3: Call generate_mermaid tool on Orchestrator
            st.divider()

            with st.spinner(f"⏳ Step 3: Generating Mermaid diagram..."):
                try:
                    # Call generate_mermaid tool directly on Orchestrator
                    mermaid_response = requests.post(
                        f"{ORCHESTRATOR_SERVICE}/execute",
                        json={
                            "tool_name": "generate_mermaid",
                            "tool_input": {
                                "query_results": all_results,
                                "entity_name": entity_name,
                                "entity_type": selected_type
                            }
                        },
                        timeout=60
                    )
                    
                    if mermaid_response.ok:
                        mermaid_data = mermaid_response.json()
                        
                        # Extract mermaid_code from ToolResult response
                        mermaid_code = ""
                        if mermaid_data.get("success"):
                            mermaid_code = mermaid_data.get("data", {}).get("mermaid_code", "")
                        elif isinstance(mermaid_data, dict) and "data" in mermaid_data:
                            mermaid_code = mermaid_data.get("data", {}).get("mermaid_code", "")
                        
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
                            st.info(f"Query returned {len(all_results)} results but Mermaid tool produced no diagram")
                    else:
                        st.error(f"Mermaid tool failed: {mermaid_response.text}")
                except Exception as e:
                    st.error(f"❌ Failed to call Mermaid tool: {str(e)}")

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