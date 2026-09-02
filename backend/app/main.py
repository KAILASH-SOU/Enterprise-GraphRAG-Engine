from contextlib import asynccontextmanager
from fastapi import FastAPI
from app.core.database import engine, neo4j_manager, qdrant_client
import logging

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

@app.get("/")
async def root():
    return {"message": "Welcome to Enterprise GraphRAG API"}

@app.get("/health")
async def health():
    return {"status": "ok"}
