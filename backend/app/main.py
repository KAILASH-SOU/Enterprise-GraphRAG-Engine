from contextlib import asynccontextmanager
from fastapi import FastAPI, UploadFile, File, Form, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from app.core.database import engine, neo4j_manager, qdrant_client, get_neo4j_session, get_safe_neo4j_session
from app.agent.router import AgenticRouter
from app.pipeline.tasks import process_document, rebuild_communities, resolve_entities_task
from app.pipeline.community_detection import run_community_detection, get_community_summaries_for_query
from app.pipeline.entity_resolution import EntityResolver
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
    tenant_id: str = Form("tenant_123")
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
    
    doc_record = {
        "id": doc_id,
        "name": file.filename,
        "status": "processing",
        "date": datetime.now().strftime("%Y-%m-%d")
    }
    DOCUMENT_DB.insert(0, doc_record)
    
    process_document.delay(tenant_id, text, {"filename": file.filename, "doc_id": doc_id})
    
    return {"message": "Upload started", "doc_id": doc_id}

@app.get("/api/documents")
async def get_documents(tenant_id: str = "tenant_123"):
    for doc in DOCUMENT_DB:
        if doc["status"] == "processing":
            doc["status"] = "completed"
            
    return DOCUMENT_DB

# --- Agent Query API ---

class QueryRequest(BaseModel):
    query: str
    tenant_id: str = "tenant_123"

@app.post("/api/query")
async def execute_query(req: QueryRequest):
    router = AgenticRouter(tenant_id=req.tenant_id)
    answer = await router.execute(req.query)
    
    strategy = await router.classify_intent(req.query)
    
    return {
        "answer": answer,
        "routing_strategy": strategy.intent,
        "reasoning": strategy.reasoning
    }

# --- Graph Visualization API ---

@app.get("/api/graph")
async def get_graph(tenant_id: str = "tenant_123"):
    nodes = []
    links = []
    
    async for session in get_neo4j_session():
        result = await session.run(
            "MATCH (n:Entity {tenant_id: $tenant_id}) RETURN n LIMIT 100",
            tenant_id=tenant_id
        )
        records = await result.data()
        
        for record in records:
            n = record["n"]
            nodes.append({
                "id": n.get("id", "Unknown"),
                "group": n.get("label", "ENTITY"),
                "val": 2
            })
            
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

# --- Community Detection API ---

class CommunityRequest(BaseModel):
    tenant_id: str = "tenant_123"

@app.post("/api/communities/rebuild")
async def rebuild_communities_endpoint(req: CommunityRequest):
    task = rebuild_communities.delay(req.tenant_id)
    return {"message": "Community rebuild started", "task_id": task.id}

@app.get("/api/communities")
async def get_communities(tenant_id: str = "tenant_123"):
    async for session in get_neo4j_session():
        result = await session.run(
            """
            MATCH (c:Community {tenant_id: $tenant_id})
            RETURN c.community_id as id, c.level as level, c.summary as summary, 
                   c.keywords as keywords, c.size as size, c.parent_community as parent
            ORDER BY c.level, c.size DESC
            """,
            tenant_id=tenant_id
        )
        records = await result.data()
        return {"communities": records}

@app.get("/api/communities/summaries")
async def get_community_summaries(query: str, tenant_id: str = "tenant_123"):
    summaries = get_community_summaries_for_query(tenant_id, query)
    return {"summaries": summaries, "query": query}

# --- Entity Resolution API ---

class EntityResolutionRequest(BaseModel):
    tenant_id: str = "tenant_123"
    entity_id: str = None
    label: str = None

@app.post("/api/entities/resolve")
async def resolve_entities_endpoint(req: EntityResolutionRequest):
    task = resolve_entities_task.delay(req.tenant_id)
    return {"message": "Entity resolution started", "task_id": task.id}

@app.get("/api/entities")
async def get_entities(tenant_id: str = "tenant_123", label: str = None):
    async for session in get_neo4j_session():
        query = "MATCH (n:Entity {tenant_id: $tenant_id})"
        params = {"tenant_id": tenant_id}
        if label:
            query += " WHERE n.label = $label"
            params["label"] = label
        query += " RETURN n LIMIT 200"
        
        result = await session.run(query, params)
        records = await result.data()
        
        entities = []
        for record in records:
            n = record["n"]
            entities.append({
                "id": n.get("id"),
                "label": n.get("label"),
                "properties": dict(n)
            })
        return {"entities": entities}

@app.post("/api/entities/merge")
async def merge_entities(
    canonical_id: str = Form(...),
    duplicate_ids: List[str] = Form(...),
    tenant_id: str = Form("tenant_123")
):
    async for session in get_safe_neo4j_session(tenant_id):
        for dup_id in duplicate_ids:
            query = """
            MATCH (dup:Entity {id: $dup_id, tenant_id: $tenant_id})
            MATCH (canon:Entity {id: $canon_id, tenant_id: $tenant_id})
            WHERE dup <> canon
            CALL apoc.refactor.mergeNodes([dup, canon], {properties: "combine"}) 
            YIELD node
            RETURN node
            """
            try:
                await session.run(query, {
                    "dup_id": dup_id,
                    "canon_id": canonical_id,
                    "tenant_id": tenant_id
                })
            except Exception:
                manual_merge = """
                MATCH (dup:Entity {id: $dup_id, tenant_id: $tenant_id})-[r]-()
                MATCH (canon:Entity {id: $canon_id, tenant_id: $tenant_id})
                WHERE dup <> canon
                MERGE (canon)-[r2:RELATION {type: type(r)}]->(endNode(r))
                SET r2 += properties(r)
                WITH dup, canon
                MATCH (dup)-[r3]-()
                DELETE r3
                DETACH DELETE dup
                """
                await session.run(manual_merge, {
                    "dup_id": dup_id,
                    "canon_id": canonical_id,
                    "tenant_id": tenant_id
                })
    return {"message": "Entities merged", "canonical_id": canonical_id, "merged": duplicate_ids}

# --- Multi-hop Reasoning API ---

class MultiHopRequest(BaseModel):
    query: str
    tenant_id: str = "tenant_123"
    max_hops: int = 3

@app.post("/api/reason/multi-hop")
async def multi_hop_reasoning(req: MultiHopRequest):
    from app.agent.multi_hop import enhanced_graph_traversal
    result = await enhanced_graph_traversal(req.tenant_id, req.query, req.max_hops)
    return result

# --- Stats API ---

@app.get("/api/stats")
async def get_stats(tenant_id: str = "tenant_123"):
    async for session in get_neo4j_session():
        entity_count = await session.run(
            "MATCH (n:Entity {tenant_id: $tenant_id}) RETURN count(n) as count",
            tenant_id=tenant_id
        )
        entity_count = (await entity_count.data())[0]["count"]
        
        rel_count = await session.run(
            "MATCH ()-[r:RELATION]->() WHERE exists((startNode(r)).tenant_id) AND startNode(r).tenant_id = $tenant_id RETURN count(r) as count",
            tenant_id=tenant_id
        )
        rel_count = (await rel_count.data())[0]["count"]
        
        comm_count = await session.run(
            "MATCH (c:Community {tenant_id: $tenant_id}) RETURN count(c) as count",
            tenant_id=tenant_id
        )
        comm_count = (await comm_count.data())[0]["count"]
        
        chunk_count = await session.run(
            "MATCH (n:Chunk {tenant_id: $tenant_id}) RETURN count(n) as count",
            tenant_id=tenant_id
        )
        chunk_count = (await chunk_count.data())[0]["count"] if chunk_count else 0
        
    return {
        "tenant_id": tenant_id,
        "entities": entity_count,
        "relationships": rel_count,
        "communities": comm_count,
        "chunks": chunk_count
    }