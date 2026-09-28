from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from neo4j import AsyncGraphDatabase
from qdrant_client import AsyncQdrantClient
from app.core.config import settings
from app.core.cypher_middleware import CypherASTMiddleware, SafeNeo4jSession
import logging

logger = logging.getLogger(__name__)

engine = create_async_engine(settings.DATABASE_URL, echo=False)
AsyncSessionLocal = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)

async def get_db():
    async with AsyncSessionLocal() as session:
        yield session


class Neo4jConnectionManager:
    def __init__(self):
        self.driver = None

    async def connect(self):
        try:
            self.driver = AsyncGraphDatabase.driver(
                settings.NEO4J_URI, 
                auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD)
            )
            logger.info("Connected to Neo4j")
        except Exception as e:
            logger.error(f"Failed to connect to Neo4j: {e}")

    async def close(self):
        if self.driver is not None:
            await self.driver.close()

    async def get_session(self):
        return self.driver.session()

neo4j_manager = Neo4jConnectionManager()

async def get_neo4j_session():
    async with await neo4j_manager.get_session() as session:
        yield session

async def get_safe_neo4j_session(tenant_id: str):
    middleware = CypherASTMiddleware(tenant_id)
    session = await neo4j_manager.get_session()
    safe_session = SafeNeo4jSession(session, middleware)
    try:
        yield safe_session
    finally:
        await session.close()

qdrant_client = AsyncQdrantClient(url=settings.QDRANT_URL)

async def get_qdrant_client():
    yield qdrant_client