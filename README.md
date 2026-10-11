# Enterprise GraphRAG Engine

An enterprise-grade Retrieval-Augmented Generation (RAG) platform built for complex, multi-hop reasoning over connected private documents. By marrying vector similarity search with Neo4j knowledge graphs, hierarchical Leiden community detection, and asynchronous task execution, the system delivers high accuracy on both local factual questions and global thematic queries.

---

## Architecture Overview

```
                        ┌─────────────────────────┐
                        │    Streamlit Frontend   │
                        │       (Port 8501)       │
                        └────────────┬────────────┘
                                     │ HTTP / REST
                                     ▼
                        ┌─────────────────────────┐
                        │     FastAPI Backend     │
                        │       (Port 8000)       │
                        └──────┬────────────┬─────┘
                               │            │
            ┌──────────────────┘            └──────────────────┐
            ▼                                                  ▼
┌─────────────────────────┐                        ┌─────────────────────────┐
│     Agentic Router      │                        │      Redis Broker       │
│  (Intent Classification)│                        │       (Port 6379)       │
└──────┬──────────────────┘                        └───────────┬─────────────┘
       │                                                       │ Tasks (LPUSH/BRPOP)
       ├──► Vector: Qdrant                                     ▼
       ├──► Graph: Multi-Hop (Neo4j)               ┌─────────────────────────┐
       └──► Global: Community Summaries (Neo4j)    │     Celery Workers      │
                                                   │   (Async Ingestion &    │
                                                   │   Leiden Detection)     │
                                                   └───────────┬─────────────┘
                                                               │
       ┌───────────────────────┬───────────────────────────────┼──────────────────────┐
       ▼                       ▼                               ▼                      ▼
┌──────────────┐      ┌─────────────────┐             ┌─────────────────┐     ┌──────────────┐
│  PostgreSQL  │      │      Neo4j      │             │     Qdrant      │     │  OpenAI API  │
│  (Metadata)  │      │(Knowledge Graph)│             │ (Vector Store)  │     │   (GPT-4o)   │
└──────────────┘      └─────────────────┘             └─────────────────┘     └──────────────┘
```

```mermaid
flowchart TD
    User["User Query / Upload"] --> UI["Streamlit Frontend (UI)"]
    UI --> API["FastAPI Backend (API Gateway)"]

    subgraph BackendOrchestration ["Core Backend Services"]
        Router["Agentic Router (GPT-4o Intent Classifier)"]
        Middleware["Cypher AST Middleware (Tenant Guard)"]
        MultiHop["Multi-Hop Reasoner (Iterative Deepening)"]
    end

    API --> Router
    API --> Middleware

    Router -->|"Factual (Cosine)"| Qdrant[("Qdrant Vector DB")]
    Router -->|"Relational (Hops)"| MultiHop
    Router -->|"Global Summary"| Neo4j[("Neo4j Knowledge Graph")]

    MultiHop -->|"Seed Entities"| Qdrant
    MultiHop -->|"Path Traversal"| Neo4j
    Middleware -->|"Tenant Injected Cypher"| Neo4j

    API -->|"Dispatch Jobs"| Redis[("Redis Broker & Backend")]
    Redis --> Workers["Celery Worker Pool"]

    subgraph BackgroundTasks ["Asynchronous Pipelines"]
        DocIngest["Document Ingestion & Chunking"]
        EntityRes["Entity Resolution (Vector + LLM Judge)"]
        CommunityDet["Hierarchical Leiden Clustering"]
    end

    Workers --> DocIngest
    Workers --> EntityRes
    Workers --> CommunityDet

    DocIngest --> Qdrant
    DocIngest --> Neo4j
    EntityRes --> Neo4j
    CommunityDet --> Neo4j
    API --> PG[("PostgreSQL (Metadata)")]

    LLM["OpenAI API (GPT-4o)"]
    Router -.-> LLM
    MultiHop -.-> LLM
    EntityRes -.-> LLM
    CommunityDet -.-> LLM
```

---

## Core Features & Implementation Details

### 1. Multi-tenant GraphRAG with Agentic Routing (`router.py`)
Traditional RAG runs a uniform vector search across every query, which fails on relational or broad structural questions. The engine uses dynamic intent classification:
* **Intent Routing:** Every query is analyzed by GPT-4o using native Pydantic structured outputs (`response_format=RoutingStrategy`) into four operational paths:
  1. `VECTOR_SEARCH`: Direct semantic lookup in Qdrant for straightforward factual retrieval.
  2. `GRAPH_TRAVERSAL`: Relational multi-hop traversal through Neo4j when reasoning across connections is required.
  3. `COMMUNITY_SUMMARY`: Global overview retrieval leveraging pre-computed hierarchical summaries.
  4. `HYBRID`: Concurrently executes both text retrieval and graph expansion, merging both contexts before final generation.
* **Pure Python Orchestration:** Implemented without heavy framework wrappers (no LangChain/LangGraph) to minimize latency, avoid abstraction leakage, and maintain full control over the execution loop.

### 2. Multi-Hop Reasoning with Iterative Deepening (`multi_hop.py`)
To resolve indirect relationships across separate documents:
* **Seed Discovery:** Query is embedded via `text-embedding-3-small` and matched in Qdrant via Approximate Nearest Neighbor (HNSW). Candidate seed entities are collected from chunk metadata and deduplicated via a hash set.
* **Iterative Deepening Search (IDS):** Traverses outward level-by-level (hops 1 to 3) via bounded Cypher queries (`[:RELATION*1..{hop}]`).
* **Cycle Prevention:** Maintains a visited hash set (`visited_entities: Set[str]`) ensuring already evaluated nodes are not re-traversed.
* **Beam Search & Heuristic LLM Path Scoring:** GPT-4o evaluates candidate paths on a `0.0 to 1.0` scale considering semantic relevance, relation types, and path conciseness. Only the top-3 paths are selected to seed the next hop, pruning explosive combinatorial expansion.
* **Cross-Document Chunk Grounding:** Identified path entities are mapped back to raw document chunks stored in Qdrant, providing the LLM with both structured graph evidence and original source text.

### 3. Entity Resolution Pipeline (`entity_resolution.py`)
Independent document extractions often produce duplicated entity variants (e.g., "Google", "Google LLC", "Alphabet Inc."):
* **Vector Cosine Similarity:** Computes cosine similarity between new and existing entity candidates.
* **LLM Judge:** When candidate similarity crosses threshold ($\ge 0.85$), GPT-4o verifies if both references describe the identical real-world entity.
* **Neo4j Graph Refactoring:** Verified duplicates are merged directly into canonical entities using `apoc.refactor.mergeNodes` (preserving all relationship edges and attributes).

### 4. Hierarchical Leiden Community Detection (`community_detection.py`)
Addresses global dataset synthesis without overflowing the LLM context window:
* **Graph Projection:** Ingests the Neo4j graph into memory via `igraph`.
* **Multi-Resolution Leiden Clustering:** Executes the Leiden algorithm (`leidenalg` with `RBConfigurationVertexPartition`) across 4 resolution parameters (`0.5`, `1.0`, `1.5`, `2.0`). Lower resolutions group broad macro-topics, while higher resolutions isolate fine-grained sub-clusters.
* **Hierarchical Tree Construction:** Maps parent-child community linkages into Neo4j (`c:Community` nodes connected via `BELONGS_TO` edges).
* **Precomputed LLM Summarization:** Celery tasks summarize each community offline via GPT-4o. Query-time global summarization yields up to a **~90% token reduction** compared to reading raw document chunks.

### 5. AST Middleware for Zero-Leakage Tenant Isolation (`cypher_middleware.py`)
Ensures strict multi-tenant privacy at the database driver layer:
* **Cypher Inspection:** Intercepts outgoing queries using regex-based AST parsing.
* **Constraint Injection:** Automatically appends `{tenant_id: "..."}` to all `Entity`, `Document`, `Chunk`, and `Community` node match patterns.
* **Safety Audit:** Validates mutating statements (`DELETE`, `DETACH DELETE`, `SET`) to block execution if valid tenant isolation guards are absent.

### 6. Asynchronous Task Architecture (Celery + Redis)
Long-running workloads (PDF chunking, entity extraction, APOC graph merges, and community clustering) run off the main event loop:
* **Decoupled API:** FastAPI dispatches jobs to Redis queues in $< 20\text{ms}$ and responds with HTTP 202.
* **Worker Execution Pool:** Celery workers consume tasks asynchronously with concurrency limits.
* **Periodic Maintenance:** Celery Beat schedules automated graph maintenance and community summary rebuilds.

---

## Architectural Tradeoffs & Engineering Decisions

| Decision | Selected Choice | Rejected Alternative | Core Engineering Rationale |
| :--- | :--- | :--- | :--- |
| **Agentic Framework** | Native Python + AsyncIO | LangGraph / LangChain | Eliminates dependency bloat, reduces call stack latency, and gives full control over state transitions and error recovery. |
| **Task Broker & Backend** | Redis | RabbitMQ | Redis simultaneously functions as both Message Broker and Result Backend in a single lightweight footprint (~20MB RAM). RabbitMQ cannot serve as a durable Celery result store without secondary storage. |
| **Clustering Algorithm** | Leiden Algorithm | Louvain Algorithm | Louvain frequently produces internally disconnected partitions. Leiden mathematically guarantees well-connected communities and converges faster. |
| **Traversal Depth** | $d = 3$ (Iterative Deepening) | Unbounded BFS ($d \ge 5$) | Limits exponential graph branching factor ($O(b^d)$) and avoids semantic drift. Deeper connections (4-5 hops) are resolved via hierarchical community summaries or bi-directional traversal. |
| **Path Selection** | LLM-Heuristic Beam Search | Exhaustive Path Scoring | Full path evaluation in dense graphs introduces unacceptable LLM API costs. Beam width of 3 limits scoring overhead to the most promising trajectories. |
| **Multi-Tenancy** | Driver-level AST Injection | Application-level manual `WHERE` clauses | Prevents accidental developer oversight from exposing cross-tenant data by enforcing isolation directly in the query pipeline. |

---

## Technology Stack

* **API Layer:** FastAPI, Uvicorn, Pydantic v2
* **Frontend:** Streamlit
* **Graph Database:** Neo4j 5.15 with APOC Plugins
* **Vector Database:** Qdrant v1.8.0
* **Relational Database:** PostgreSQL 15
* **Task Queue & Caching:** Celery, Redis 7 (Alpine)
* **Graph Algorithms:** python-igraph, leidenalg, NetworkX
* **LLM & Embeddings:** OpenAI GPT-4o, text-embedding-3-small
* **Containerization:** Docker, Docker Compose

---

## Project Structure

```
Enterprise-GraphRAG-Engine/
├── backend/
│   ├── app/
│   │   ├── agent/
│   │   │   ├── router.py             # Agentic intent routing & context synthesis
│   │   │   ├── multi_hop.py          # Iterative deepening & heuristic path scoring
│   │   │   └── __init__.py
│   │   ├── core/
│   │   │   ├── config.py             # Pydantic environment configurations
│   │   │   ├── database.py           # Connections: Postgres, Neo4j, Qdrant
│   │   │   ├── cypher_middleware.py  # AST middleware for tenant isolation
│   │   │   └── security.py           # JWT authentication
│   │   ├── pipeline/
│   │   │   ├── tasks.py              # Celery tasks (ingestion, community rebuild)
│   │   │   ├── entity_resolution.py  # Vector matching, LLM judge & APOC merge
│   │   │   ├── community_detection.py # Leiden hierarchical summaries
│   │   │   ├── schema.py             # Pydantic extraction models
│   │   │   └── __init__.py
│   │   ├── dependencies/
│   │   │   └── auth.py               # Authentication & tenant dependencies
│   │   └── main.py                   # FastAPI REST route definitions
│   ├── scripts/
│   │   └── init-postgres.sql         # Database table schema init
│   ├── Dockerfile
│   ├── entrypoint.sh
│   └── requirements.txt
├── frontend/
│   ├── streamlit_app.py              # Interactive multi-page UI
│   ├── Dockerfile
│   └── requirements.txt
├── docker-compose.yml                # Multi-service stack composition
├── .env.example
├── LICENSE
└── README.md
```

---

## Getting Started

### Prerequisites
* Docker & Docker Compose
* OpenAI API Key

### 1. Environment Configuration
Create a `.env` file in the root directory:
```bash
cp .env.example .env
```
Ensure your OpenAI API key and service credentials are configured:
```env
OPENAI_API_KEY=sk-...
DATABASE_URL=postgresql+asyncpg://postgres:password@postgres:5432/graphrag
NEO4J_URI=bolt://neo4j:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=password
QDRANT_URL=http://qdrant:6333
REDIS_URL=redis://redis:6379/0
JWT_SECRET_KEY=supersecretkey
```

### 2. Launch Services
Start the entire stack using Docker Compose:
```bash
docker-compose up --build
```

The composition spins up:
* **PostgreSQL:** Port `5432`
* **Neo4j Browser:** Port `7474`, Bolt: `7687`
* **Qdrant Vector DB:** Port `6333`
* **Redis Broker:** Port `6379`
* **FastAPI Backend:** Port `8000` (Docs: `http://localhost:8000/docs`)
* **Celery Worker & Celery Beat:** Background pipeline execution
* **Streamlit UI:** Port `8501` (`http://localhost:8501`)

---

## API Reference

### Ingestion & Documents
* `POST /api/upload`: Upload PDF or text documents for async ingestion.
* `GET /api/documents`: List uploaded documents and status for current tenant.

### Querying & Reasoning
* `POST /api/query`: Execute an agentic GraphRAG query with automatic intent routing.
* `POST /api/reason/multi-hop`: Trigger targeted multi-hop graph traversal with scored paths.

### Graph & Communities
* `GET /api/graph`: Export graph nodes and relations for visual rendering.
* `GET /api/communities`: Retrieve hierarchical communities.
* `POST /api/communities/rebuild`: Asynchronously trigger Leiden community re-clustering.
* `GET /api/communities/summaries`: Search through community summaries.

### Entity Management
* `GET /api/entities`: Fetch entities filtered by label.
* `POST /api/entities/resolve`: Trigger asynchronous deduplication and resolution.
* `POST /api/entities/merge`: Manually merge duplicate entity nodes.

---

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.