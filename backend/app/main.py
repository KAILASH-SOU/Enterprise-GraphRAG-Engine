from contextlib import asynccontextmanager
from fastapi import FastAPI, UploadFile, File, Form, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from app.core.database import engine, neo4j_manager, qdrant_client, get_neo4j_session
from app.agent.router import AgenticRouter
from app.pipeline.tasks import process_document
import logging
import uuid
from datetime import datetime
from typing import List, Dict, Any

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Starting up Enterprise GraphRAG Backend")
    await neo4j_manager.connect()
    try:
        await qdrant_client.get_collections()
        logger.info("Connected to Qdrant")
    except Exception as e:
        logger.error(f"Failed to connect to Qdrant: {e}")
    
    yield
    
    # Shutdown
    logger.info("Shutting down...")
    await neo4j_manager.close()
    await engine.dispose()
    await qdrant_client.close()

app = FastAPI(title="Enterprise GraphRAG Engine", lifespan=lifespan)

# CORS configuration for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Allow all for local dev
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mock DB for tracking document statuses
DOCUMENT_DB = []

@app.get("/")
async def root():
    return {"message": "Welcome to Enterprise GraphRAG API"}

@app.get("/health")
async def health():
    return {"status": "ok"}

# --- Document Management API ---

@app.post("/api/upload")
async def upload_document(
    file: UploadFile = File(...),
    tenant_id: str = Form("tenant_123") # Default tenant for MVP
):
    doc_id = str(uuid.uuid4())
    content = await file.read()
    
    if file.filename.lower().endswith(".pdf"):
        import io
        from pypdf import PdfReader
        pdf = PdfReader(io.BytesIO(content))
        text = "\n".join(page.extract_text() or "" for page in pdf.pages)
    else:
        text = content.decode("utf-8")
    
    # Record document
    doc_record = {
        "id": doc_id,
        "name": file.filename,
        "status": "processing",
        "date": datetime.now().strftime("%Y-%m-%d")
    }
    DOCUMENT_DB.insert(0, doc_record)
    
    # Trigger celery task
    process_document.delay(tenant_id, text, {"filename": file.filename, "doc_id": doc_id})
    
    return {"message": "Upload started", "doc_id": doc_id}

@app.get("/api/documents")
async def get_documents(tenant_id: str = "tenant_123"):
    # In a real app, query Postgres. Here we return the mock DB.
    # Note: Because the Celery worker operates async, we will simulate completion 
    # of the first document if they ask for it.
    for doc in DOCUMENT_DB:
        if doc["status"] == "processing":
            # Just mock completing it immediately for UX
            doc["status"] = "completed"
            
    return DOCUMENT_DB

# --- Agent Query API ---

class QueryRequest(BaseModel):
    query: str
    tenant_id: str = "tenant_123"

@app.post("/api/query")
async def execute_query(req: QueryRequest):
    router = AgenticRouter(tenant_id=req.tenant_id)
    # The router execute method determines intent, fetches context from Vector/Graph, and generates answer
    answer = await router.execute(req.query)
    
    # We'll re-run intent just to pass it to the frontend for UI display
    strategy = await router.classify_intent(req.query)
    
    return {
        "answer": answer,
        "routing_strategy": strategy.intent,
        "reasoning": strategy.reasoning
    }

# --- Graph Visualization API ---

@app.get("/api/graph")
async def get_graph(tenant_id: str = "tenant_123"):
    """
    Returns graph data in a format suitable for react-force-graph-2d.
    { "nodes": [...], "links": [...] }
    """
    nodes = []
    links = []
    
    async for session in get_neo4j_session():
        # Get nodes
        result = await session.run(
            "MATCH (n:Entity {tenant_id: $tenant_id}) RETURN n LIMIT 100",
            tenant_id=tenant_id
        )
        records = await result.data()
        
        for record in records:
            n = record["n"]
            # format for react-force-graph: { id: "...", group: "...", val: ... }
            nodes.append({
                "id": n.get("id", "Unknown"),
                "group": n.get("label", "ENTITY"),
                "val": 2
            })
            
        # Get edges
        result = await session.run(
            "MATCH (source:Entity {tenant_id: $tenant_id})-[r]->(target:Entity {tenant_id: $tenant_id}) RETURN source.id as source_id, target.id as target_id, type(r) as label LIMIT 200",
            tenant_id=tenant_id
        )
        records = await result.data()
        
        for record in records:
            links.append({
                "source": record["source_id"],
                "target": record["target_id"],
                "label": record["label"]
            })
            
    return {"nodes": nodes, "links": links}
