import streamlit as st
import requests

API_BASE = "http://gateway:8000"  # docker DNS

st.set_page_config(page_title="MultiAgent MCP", layout="wide")

st.title("🧠 Agentic Codebase Chat")

# ---- Session memory ----
if "session_id" not in st.session_state:
    st.session_state.session_id = None
if "messages" not in st.session_state:
    st.session_state.messages = []

# ---- Index repo ----
with st.sidebar:
    st.header("📦 Index Repository")
    repo_url = st.text_input("GitHub repo URL")

    if st.button("Start Indexing"):
        res = requests.post(
            f"{API_BASE}/api/index",
            json={"repo_url": repo_url}
        )
        if res.ok:
            st.success("Indexing started")
        else:
            st.error(res.text)

# ---- Chat UI ----
for msg in st.session_state.messages:
    st.chat_message(msg["role"]).write(msg["content"])

query = st.chat_input("Ask about the codebase...")

if query:
    st.chat_message("user").write(query)

    payload = {
        "query": query,
        "session_id": st.session_state.session_id
    }

    res = requests.post(f"{API_BASE}/api/rag-chat", json=payload)

    if res.ok:
        data = res.json()
        st.session_state.session_id = data["session_id"]

        answer = data["response"]
        st.chat_message("assistant").write(answer)

        st.session_state.messages.append({"role": "user", "content": query})
        st.session_state.messages.append({"role": "assistant", "content": answer})
    else:
        st.error(res.text)
