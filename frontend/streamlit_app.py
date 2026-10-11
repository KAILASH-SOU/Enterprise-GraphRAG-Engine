import streamlit as st
import requests
import json
import pandas as pd
import plotly.graph_objects as go
import networkx as nx
from streamlit_agraph import agraph, Node, Edge, Config
import time
from typing import Dict, Any, List

# Page config
st.set_page_config(
    page_title="Enterprise GraphRAG Engine",
    layout="wide",
    initial_sidebar_state="expanded"
)

# API Base URL
API_BASE = "http://localhost:8000"

# Custom CSS
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        font-weight: 700;
        color: #1e3a8a;
        margin-bottom: 1rem;
    }
    .sub-header {
        font-size: 1.5rem;
        font-weight: 600;
        color: #3b82f6;
        margin-top: 1.5rem;
        margin-bottom: 0.5rem;
    }
    .metric-card {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        padding: 1rem;
        border-radius: 10px;
        color: white;
        text-align: center;
    }
    .stButton > button {
        background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        color: white;
        border: none;
        border-radius: 5px;
        padding: 0.5rem 1rem;
        font-weight: 600;
    }
    .stButton > button:hover {
        background: linear-gradient(135deg, #5a6fd6 0%, #6a4190 100%);
    }
    .chat-message {
        padding: 1rem;
        border-radius: 10px;
        margin-bottom: 1rem;
    }
    .user-message {
        background: #e0f2fe;
        border-left: 4px solid #3b82f6;
    }
    .assistant-message {
        background: #f0fdf4;
        border-left: 4px solid #22c55e;
    }
    .strategy-badge {
        display: inline-block;
        padding: 0.25rem 0.75rem;
        border-radius: 9999px;
        font-size: 0.75rem;
        font-weight: 600;
        margin-right: 0.5rem;
    }
    .strategy-vector { background: #dbeafe; color: #1e40af; }
    .strategy-graph { background: #fef3c7; color: #92400e; }
    .strategy-hybrid { background: #dcfce7; color: #166534; }
    .strategy-community { background: #fce7f3; color: #9d174d; }
</style>
""", unsafe_allow_html=True)

# Session state initialization
if "messages" not in st.session_state:
    st.session_state.messages = []
if "tenant_id" not in st.session_state:
    st.session_state.tenant_id = "tenant_123"
if "documents" not in st.session_state:
    st.session_state.documents = []
if "graph_data" not in st.session_state:
    st.session_state.graph_data = {"nodes": [], "links": []}
if "communities" not in st.session_state:
    st.session_state.communities = []
if "stats" not in st.session_state:
    st.session_state.stats = {}

# Helper functions
def api_get(endpoint: str, params: Dict = None) -> Dict:
    try:
        response = requests.get(f"{API_BASE}{endpoint}", params=params, timeout=30)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        st.error(f"API Error: {e}")
        return {}

def api_post(endpoint: str, data: Dict = None, files: Dict = None) -> Dict:
    try:
        if files:
            response = requests.post(f"{API_BASE}{endpoint}", files=files, data=data, timeout=60)
        else:
            response = requests.post(f"{API_BASE}{endpoint}", json=data, timeout=60)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        st.error(f"API Error: {e}")
        return {}

def load_documents():
    result = api_get("/api/documents", {"tenant_id": st.session_state.tenant_id})
    st.session_state.documents = result if isinstance(result, list) else []

def load_graph():
    result = api_get("/api/graph", {"tenant_id": st.session_state.tenant_id})
    st.session_state.graph_data = result if isinstance(result, dict) else {"nodes": [], "links": []}

def load_communities():
    result = api_get("/api/communities", {"tenant_id": st.session_state.tenant_id})
    st.session_state.communities = result.get("communities", []) if isinstance(result, dict) else []

def load_stats():
    result = api_get("/api/stats", {"tenant_id": st.session_state.tenant_id})
    st.session_state.stats = result if isinstance(result, dict) else {}

# Sidebar
with st.sidebar:
    st.markdown('<div class="main-header">GraphRAG Engine</div>', unsafe_allow_html=True)
    
    # Tenant selection
    st.session_state.tenant_id = st.text_input(
        "Tenant ID", 
        value=st.session_state.tenant_id,
        help="Multi-tenant isolation identifier"
    )
    
    st.divider()
    
    # Navigation
    page = st.radio(
        "Navigation",
        ["Chat", "Documents", "Graph Explorer", "Communities", "Multi-hop Reasoning", "Stats"],
        label_visibility="collapsed"
    )
    
    st.divider()
    
    # Quick actions
    st.markdown("### Quick Actions")
    if st.button("Refresh All Data"):
        load_documents()
        load_graph()
        load_communities()
        load_stats()
        st.success("Data refreshed!")
    
    if st.button("Rebuild Communities"):
        result = api_post("/api/communities/rebuild", {"tenant_id": st.session_state.tenant_id})
        if result:
            st.success(f"Community rebuild started: {result.get('task_id', '')}")
    
    if st.button("Resolve Entities"):
        result = api_post("/api/entities/resolve", {"tenant_id": st.session_state.tenant_id})
        if result:
            st.success(f"Entity resolution started: {result.get('task_id', '')}")

# Main content
if page == "Chat":
    st.markdown('<div class="main-header">GraphRAG Chat</div>', unsafe_allow_html=True)
    st.markdown("Ask questions about your documents. The system automatically routes to vector search, graph traversal, or community summaries.")
    
    # Display chat history
    for msg in st.session_state.messages:
        if msg["role"] == "user":
            st.markdown(f'<div class="chat-message user-message"><strong>You:</strong> {msg["content"]}</div>', unsafe_allow_html=True)
        else:
            strategy_class = f"strategy-{msg.get('strategy', '').lower()}"
            st.markdown(f'''
            <div class="chat-message assistant-message">
                <strong>Assistant:</strong> {msg["content"]}
                <br><br>
                <span class="strategy-badge {strategy_class}">{msg.get("strategy", "UNKNOWN")}</span>
                <small style="color: #666;">{msg.get("reasoning", "")}</small>
            </div>
            ''', unsafe_allow_html=True)
    
    # Chat input
    with st.form("chat_form", clear_on_submit=True):
        col1, col2 = st.columns([5, 1])
        with col1:
            user_query = st.text_input("Your question", placeholder="e.g., What are the key relationships between entities in the documents?", label_visibility="collapsed")
        with col2:
            submitted = st.form_submit_button("Send", use_container_width=True)
    
    if submitted and user_query:
        st.session_state.messages.append({"role": "user", "content": user_query})
        
        with st.spinner("Thinking..."):
            result = api_post("/api/query", {"query": user_query, "tenant_id": st.session_state.tenant_id})
        
        if result:
            st.session_state.messages.append({
                "role": "assistant",
                "content": result.get("answer", "No response"),
                "strategy": result.get("routing_strategy", "UNKNOWN"),
                "reasoning": result.get("reasoning", "")
            })
        st.rerun()

elif page == "Documents":
    st.markdown('<div class="main-header">Document Management</div>', unsafe_allow_html=True)
    
    # Upload section
    with st.expander("Upload New Document", expanded=True):
        uploaded_file = st.file_uploader(
            "Choose a file",
            type=["pdf", "txt", "md"],
            help="Upload PDF or text documents for processing"
        )
        
        if uploaded_file and st.button("Upload & Process"):
            with st.spinner("Uploading and processing..."):
                files = {"file": (uploaded_file.name, uploaded_file.getvalue(), uploaded_file.type)}
                data = {"tenant_id": st.session_state.tenant_id}
                result = api_post("/api/upload", data=data, files=files)
                
                if result:
                    st.success(f"Upload started! Doc ID: {result.get('doc_id', 'unknown')}")
                    time.sleep(1)
                    load_documents()
                    st.rerun()
    
    # Document list
    st.markdown('<div class="sub-header">Document List</div>', unsafe_allow_html=True)
    
    if st.button("Refresh Documents"):
        load_documents()
        st.rerun()
    
    if st.session_state.documents:
        df = pd.DataFrame(st.session_state.documents)
        st.dataframe(
            df[["id", "name", "status", "date"]],
            use_container_width=True,
            hide_index=True
        )
    else:
        st.info("No documents uploaded yet. Upload a document to get started.")

elif page == "Graph Explorer":
    st.markdown('<div class="main-header">Knowledge Graph Explorer</div>', unsafe_allow_html=True)
    
    col1, col2 = st.columns([3, 1])
    
    with col2:
        st.markdown("### Graph Controls")
        if st.button("Load Graph"):
            with st.spinner("Loading graph..."):
                load_graph()
            st.success(f"Loaded {len(st.session_state.graph_data.get('nodes', []))} nodes, {len(st.session_state.graph_data.get('links', []))} edges")
        
        max_nodes = st.slider("Max Nodes", 10, 200, 100)
        physics = st.checkbox("Enable Physics", value=True)
    
    with col1:
        if st.session_state.graph_data.get("nodes"):
            # Convert to streamlit-agraph format
            nodes = []
            for n in st.session_state.graph_data["nodes"][:max_nodes]:
                nodes.append(Node(
                    id=n["id"],
                    label=n["id"][:30],
                    size=20,
                    color="#3b82f6" if n.get("group") == "ENTITY" else "#22c55e",
                    title=f"Label: {n.get('group', 'N/A')}"
                ))
            
            edges = []
            for link in st.session_state.graph_data["links"][:200]:
                edges.append(Edge(
                    source=link["source"],
                    target=link["target"],
                    label=link.get("label", ""),
                    color="#94a3b8"
                ))
            
            config = Config(
                width=800,
                height=600,
                directed=True,
                physics=physics,
                hierarchical=False,
                nodeHighlightBehavior=True,
                highlightColor="#f59e0b",
                collapsible=True
            )
            
            return_value = agraph(nodes=nodes, edges=edges, config=config)
        else:
            st.info("Click 'Load Graph' to visualize the knowledge graph")

elif page == "Communities":
    st.markdown('<div class="main-header">Hierarchical Communities</div>', unsafe_allow_html=True)
    st.markdown("Leiden community detection with hierarchical summaries for global query answering.")
    
    col1, col2 = st.columns([2, 1])
    
    with col2:
        if st.button("Load Communities"):
            with st.spinner("Loading communities..."):
                load_communities()
            st.success(f"Loaded {len(st.session_state.communities)} communities")
        
        # Community summary search
        st.markdown("### Search Summaries")
        summary_query = st.text_input("Query for relevant communities", placeholder="e.g., financial relationships")
        if st.button("Search") and summary_query:
            with st.spinner("Searching..."):
                result = api_get("/api/communities/summaries", {"query": summary_query, "tenant_id": st.session_state.tenant_id})
                if result.get("summaries"):
                    st.markdown("**Relevant Communities:**")
                    st.markdown(result["summaries"])
    
    with col1:
        if st.session_state.communities:
            # Group by level
            df = pd.DataFrame(st.session_state.communities)
            
            for level in sorted(df["level"].unique()):
                level_df = df[df["level"] == level]
                with st.expander(f"Level {level} ({len(level_df)} communities)", expanded=level==0):
                    for _, row in level_df.iterrows():
                        st.markdown(f"""
                        **Community {row['id']}** (Size: {row['size']})
                        - Summary: {row['summary'][:200]}...
                        - Keywords: {', '.join(row['keywords'][:5])}
                        - Parent: {row['parent'] if row['parent'] else 'None'}
                        """)
        else:
            st.info("No communities loaded. Click 'Load Communities' or 'Rebuild Communities' in sidebar.")

elif page == "Multi-hop Reasoning":
    st.markdown('<div class="main-header">Multi-hop Reasoning</div>', unsafe_allow_html=True)
    st.markdown("Perform iterative graph traversal with LLM-scored paths and cross-document retrieval.")
    
    with st.form("multi_hop_form"):
        query = st.text_area("Query", placeholder="e.g., How does Entity A connect to Entity B through intermediate relationships?", height=100)
        max_hops = st.slider("Max Hops", 1, 5, 3)
        submitted = st.form_submit_button("Run Multi-hop Reasoning", use_container_width=True)
    
    if submitted and query:
        with st.spinner(f"Running {max_hops}-hop reasoning..."):
            result = api_post("/api/reason/multi-hop", {
                "query": query,
                "tenant_id": st.session_state.tenant_id,
                "max_hops": max_hops
            })
        
        if result:
            st.markdown("### Results")
            
            # Context string
            if result.get("context_string"):
                st.markdown("**Reasoning Context:**")
                st.code(result["context_string"])
            
            # Paths
            if result.get("graph_paths"):
                st.markdown("**Graph Paths Found:**")
                for i, (path, score, reasoning) in enumerate(zip(
                    result["graph_paths"], 
                    result.get("path_scores", []),
                    result.get("path_reasoning", [])
                )):
                    with st.expander(f"Path {i+1} (Score: {score:.2f})"):
                        st.markdown(f"**Path:** {' → '.join(path)}")
                        st.markdown(f"**Reasoning:** {reasoning}")
            
            # Cross-document chunks
            if result.get("cross_document_chunks"):
                st.markdown("**Cross-Document Context:**")
                for chunk in result["cross_document_chunks"][:3]:
                    st.markdown(f"- {chunk.get('text', '')[:300]}...")

elif page == "Stats":
    st.markdown('<div class="main-header">System Statistics</div>', unsafe_allow_html=True)
    
    if st.button("Refresh Stats"):
        load_stats()
        st.rerun()
    
    if st.session_state.stats:
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            st.markdown(f'''
            <div class="metric-card">
                <h3>{st.session_state.stats.get("entities", 0)}</h3>
                <p>Entities</p>
            </div>
            ''', unsafe_allow_html=True)
        
        with col2:
            st.markdown(f'''
            <div class="metric-card">
                <h3>{st.session_state.stats.get("relationships", 0)}</h3>
                <p>Relationships</p>
            </div>
            ''', unsafe_allow_html=True)
        
        with col3:
            st.markdown(f'''
            <div class="metric-card">
                <h3>{st.session_state.stats.get("communities", 0)}</h3>
                <p>Communities</p>
            </div>
            ''', unsafe_allow_html=True)
        
        with col4:
            st.markdown(f'''
            <div class="metric-card">
                <h3>{st.session_state.stats.get("chunks", 0)}</h3>
                <p>Chunks</p>
            </div>
            ''', unsafe_allow_html=True)
        
        st.divider()
        
        # Entity list
        st.markdown('<div class="sub-header">Entity Browser</div>', unsafe_allow_html=True)
        entity_label = st.selectbox("Filter by label", ["All", "PERSON", "ORGANIZATION", "CONCEPT", "LOCATION", "EVENT"])
        
        if st.button("Load Entities"):
            with st.spinner("Loading entities..."):
                label = None if entity_label == "All" else entity_label
                result = api_get("/api/entities", {"tenant_id": st.session_state.tenant_id, "label": label})
                entities = result.get("entities", [])
                
                if entities:
                    df = pd.DataFrame(entities)
                    st.dataframe(df[["id", "label"]], use_container_width=True, hide_index=True)
                else:
                    st.info("No entities found")
    else:
        st.info("Click 'Refresh Stats' to load statistics")

# Footer
st.divider()
st.markdown(
    "<center>Enterprise GraphRAG Engine | Built with FastAPI + Streamlit + Neo4j + Qdrant</center>",
    unsafe_allow_html=True
)