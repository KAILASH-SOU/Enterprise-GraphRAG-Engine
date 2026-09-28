# Enterprise GraphRAG Engine

An advanced retrieval-augmented generation system designed for complex, multi-hop reasoning over enterprise data. Combines vector similarity search with graph traversal and hierarchical community summaries for agentic question answering.

## Features Implemented

### 1. Multi-tenant GraphRAG with Multi-hop Reasoning
- **Agentic routing**: Classifies queries into VECTOR_SEARCH, GRAPH_TRAVERSAL, HYBRID, or COMMUNITY_SUMMARY
- **Iterative deepening**: Multi-hop graph traversal with LLM-scored path relevance
- **Cross-document retrieval**: Finds relevant chunks across documents using extracted entities

### 2. Entity Resolution Pipeline
- **Vector similarity deduplication**: Embeds entities and finds similar ones using cosine similarity
- **LLM-based alias merging**: Uses GPT-4o to judge if entities are the same real-world entity
- **Automatic merge in Neo4j**: Combines duplicate nodes preserving relationships

### 3. Leiden Community Detection for Hierarchical Summaries
- **Multi-resolution community detection**: Runs Leiden algorithm at multiple resolutions (0.5, 1.0, 1.5, 2.0)
- **Hierarchical summaries**: Builds parent-child community relationships
- **LLM-generated summaries**: GPT-4o creates concise summaries for each community
- **Token reduction**: Pre-computed summaries reduce LLM token usage by ~90% for global queries

### 4. AST Middleware for Zero-Leakage Tenant Isolation
- **Cypher pattern parsing**: Extracts node patterns from queries using regex-based AST parsing
- **Automatic tenant injection**: Injects `tenant_id` constraints into all Entity/Document/Chunk/Community patterns
- **Query validation**: Validates queries for safety before execution
- **Transparent wrapping**: Works with existing Neo4j session/transaction APIs

### 5. Streamlit Frontend
- **Chat interface**: Agentic query with strategy display
- **Document management**: Upload PDFs/text with progress tracking
- **Graph explorer**: Interactive force-directed graph visualization
- **Community browser**: Hierarchical community summaries with search
- **Multi-hop reasoning**: Dedicated page for iterative graph traversal
- **Statistics dashboard**: Real-time entity/relationship/community counts

## Architecture

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   Streamlit     │────▶│    FastAPI      │────▶│   Celery        │
│   Frontend      │     │   Backend       │     │   Workers       │
└─────────────────┘     └────────┬────────┘     └────────┬────────┘
                                 │                       │
        ┌────────────────────────┼───────────────────────┼────────────────────────┐
        ▼                        ▼                       ▼                        ▼
┌───────────────┐        ┌───────────────┐        ┌───────────────┐        ┌───────────────┐
│   PostgreSQL  │        │    Neo4j      │        │    Qdrant     │        │     Redis     │
│  (Metadata)   │        │  (Knowledge   │        │  (Vectors)    │        │   (Queue)     │
│               │        │   Graph)      │        │               │        │               │
└───────────────┘        └───────────────┘        └───────────────┘        └───────────────┘
```

## Project Structure

```
Enterprise-GraphRAG-Engine/
├── backend/
│   ├── app/
│   │   ├── agent/
│   │   │   ├── router.py          # Agentic routing with intent classification
│   │   │   ├── multi_hop.py       # Multi-hop reasoning with iterative deepening
│   │   │   └── __init__.py
│   │   ├── core/
│   │   │   ├── config.py          # Pydantic settings
│   │   │   ├── database.py        # DB connections (Postgres, Neo4j, Qdrant)
│   │   │   ├── cypher_middleware.py  # AST middleware for tenant isolation
│   │   │   └── security.py        # JWT auth
│   │   ├── pipeline/
│   │   │   ├── tasks.py           # Celery tasks (document processing, communities)
│   │   │   ├── entity_resolution.py  # Entity deduplication & merging
│   │   │   ├── community_detection.py  # Leiden hierarchical summaries
│   │   │   ├── schema.py          # Pydantic models for graph extraction
│   │   │   └── __init__.py
│   │   ├── dependencies/
│   │   │   └── auth.py            # FastAPI auth dependencies
│   │   └── main.py                # FastAPI routes
│   ├── requirements.txt
│   ├── Dockerfile
│   └── entrypoint.sh
├── frontend/
│   ├── streamlit_app.py           # Streamlit frontend
│   ├── requirements.txt
│   └── Dockerfile
├── docker-compose.yml
└── .env.example
```

## Quick Start

### Prerequisites
- Docker and Docker Compose
- OpenAI API Key

### 1. Configure Environment
```bash
cp .env.example .env
# Edit .env and add your OPENAI_API_KEY
```

### 2. Start Full Stack
```bash
docker-compose up --build
```

This starts:
- **PostgreSQL** (port 5432)
- **Neo4j** (ports 7474, 7687) with APOC plugin
- **Qdrant** (port 6333)
- **Redis** (port 6379)
- **FastAPI Backend** (port 8000)
- **Celery Worker** (document processing)
- **Celery Beat** (scheduled tasks)
- **Streamlit Frontend** (port 8501)

### 3. Access Applications
- **Streamlit UI**: http://localhost:8501
- **FastAPI Docs**: http://localhost:8000/docs
- **Neo4j Browser**: http://localhost:7474

## API Endpoints

### Document Management
- `POST /api/upload` - Upload PDF/text document
- `GET /api/documents` - List documents

### Query & Reasoning
- `POST /api/query` - Agentic GraphRAG query
- `POST /api/reason/multi-hop` - Multi-hop reasoning with path scoring

### Graph & Communities
- `GET /api/graph` - Graph data for visualization
- `GET /api/communities` - List all communities
- `POST /api/communities/rebuild` - Trigger community detection
- `GET /api/communities/summaries` - Search community summaries

### Entity Resolution
- `GET /api/entities` - List entities
- `POST /api/entities/resolve` - Trigger entity resolution
- `POST /api/entities/merge` - Merge duplicate entities

### Statistics
- `GET /api/stats` - System statistics

## Development

### Backend Only
```bash
cd backend
pip install -r requirements.txt
cp .env.example .env  # Add OPENAI_API_KEY
uvicorn app.main:app --reload
# In another terminal:
celery -A app.pipeline.tasks.celery_app worker --loglevel=info
```

### Frontend Only
```bash
cd frontend
pip install -r requirements.txt
streamlit run streamlit_app.py
```

## Key Implementation Details

### Entity Resolution Flow
```
New Entity → Embed → Vector Search (similar entities) 
          → LLM Judge (same entity?) → Merge in Neo4j
```

### Community Detection Flow
```
Graph → iGraph → Leiden (multi-resolution) 
      → Hierarchical clustering → LLM Summaries 
      → Store in Neo4j (Community nodes + BELONGS_TO edges)
```

### Multi-hop Reasoning Flow
```
Query → Seed entities (vector search) 
      → Iterative hops (1→2→3) with LLM path scoring
      → Cross-document chunk retrieval
      → Synthesized context → Answer
```

### Tenant Isolation
All queries automatically get `tenant_id` constraints injected via `CypherASTMiddleware`, preventing cross-tenant data leakage even if queries are malformed.

## Configuration

Key environment variables:
| Variable | Description |
|----------|-------------|
| `OPENAI_API_KEY` | Required for embeddings & LLM |
| `DATABASE_URL` | PostgreSQL connection |
| `NEO4J_URI` | Neo4j Bolt URL |
| `QDRANT_URL` | Qdrant HTTP URL |
| `REDIS_URL` | Redis for Celery |
| `JWT_SECRET_KEY` | JWT signing key |

## License

MIT