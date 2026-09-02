import os
import json
import uuid
import logging
from celery import Celery
from neo4j import GraphDatabase
from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct, VectorParams, Distance
from openai import OpenAI
from app.pipeline.schema import GraphExtraction
from app.core.config import settings

logger = logging.getLogger(__name__)

celery_app = Celery(
    "graphrag_pipeline",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
)

# Synchronous clients for Celery worker
neo4j_driver = GraphDatabase.driver(
    settings.NEO4J_URI, auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD)
)
qdrant_sync = QdrantClient(url=settings.QDRANT_URL)
openai_client = OpenAI(api_key=settings.OPENAI_API_KEY)

# Ensure Qdrant collection exists (lazy init)
try:
    qdrant_sync.create_collection(
        collection_name="chunks",
        vectors_config=VectorParams(size=1536, distance=Distance.COSINE),
    )
except Exception:
    pass # Collection already exists

def chunk_text(text: str, chunk_size: int = 1500, overlap: int = 300) -> list[str]:
    # Simplistic chunking by characters for this implementation
    chunks = []
    start = 0
    text_length = len(text)
    
    while start < text_length:
        end = start + chunk_size
        chunks.append(text[start:end])
        start += chunk_size - overlap
    return chunks

def extract_graph(text_chunk: str) -> GraphExtraction:
    if not settings.OPENAI_API_KEY:
        logger.warning("OPENAI_API_KEY not set, using mock extraction.")
        return GraphExtraction(nodes=[], edges=[])

    try:
        response = openai_client.beta.chat.completions.parse(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are a knowledge graph extraction engine. Extract entities and relationships from the provided text."},
                {"role": "user", "content": text_chunk}
            ],
            response_format=GraphExtraction,
        )
        return response.choices[0].message.parsed
    except Exception as e:
        logger.error(f"LLM Extraction failed: {e}")
        return GraphExtraction(nodes=[], edges=[])

def ingest_to_neo4j(tenant_id: str, extraction: GraphExtraction, chunk_id: str):
    def _merge_tx(tx, tenant_id, extraction, chunk_id):
        for node in extraction.nodes:
            query = """
            MERGE (n:Entity {id: $id, tenant_id: $tenant_id})
            SET n.label = $label, n += $properties
            """
            tx.run(query, id=node.id, tenant_id=tenant_id, label=node.label, properties=node.properties)
        
        for edge in extraction.edges:
            query = """
            MATCH (source:Entity {id: $source_id, tenant_id: $tenant_id})
            MATCH (target:Entity {id: $target_id, tenant_id: $tenant_id})
            MERGE (source)-[r:RELATION {type: $relation_type}]->(target)
            SET r += $properties, r.chunk_id = $chunk_id
            """
            tx.run(query, 
                   source_id=edge.source_id, 
                   target_id=edge.target_id, 
                   tenant_id=tenant_id, 
                   relation_type=edge.relation_type,
                   properties=edge.properties,
                   chunk_id=chunk_id)
            
    with neo4j_driver.session() as session:
        session.execute_write(_merge_tx, tenant_id, extraction, chunk_id)

@celery_app.task(name="process_document")
def process_document(tenant_id: str, document_text: str, doc_metadata: dict):
    logger.info(f"Starting processing for tenant {tenant_id}")
    chunks = chunk_text(document_text)
    
    for idx, chunk in enumerate(chunks):
        chunk_id = str(uuid.uuid4())
        
        embedding = []
        if settings.OPENAI_API_KEY:
            try:
                emb_res = openai_client.embeddings.create(input=chunk, model="text-embedding-3-small")
                embedding = emb_res.data[0].embedding
            except Exception as e:
                logger.error(f"Embedding failed: {e}")
        
        if not embedding:
            embedding = [0.0] * 1536
        
        extraction = extract_graph(chunk)
        ingest_to_neo4j(tenant_id, extraction, chunk_id)
        
        payload = {
            "tenant_id": tenant_id,
            "text": chunk,
            "chunk_id": chunk_id,
            **doc_metadata
        }
        
        node_ids = [n.id for n in extraction.nodes]
        if node_ids:
            payload["extracted_nodes"] = node_ids
            
        qdrant_sync.upsert(
            collection_name="chunks",
            points=[
                PointStruct(
                    id=chunk_id,
                    vector=embedding,
                    payload=payload
                )
            ]
        )
        
    logger.info(f"Completed processing for tenant {tenant_id}, chunks: {len(chunks)}")
    return {"status": "success", "chunks_processed": len(chunks)}
