# Enterprise GraphRAG Engine

Enterprise GraphRAG Engine is an advanced retrieval-augmented generation system designed for complex, multi-hop reasoning over enterprise data. By combining vector similarity search with graph traversal, it provides an agentic approach to answering complex questions accurately.

## Project Architecture

The system is built on a modern, decoupled architecture leveraging robust databases for specialized data structures.

### High-Level Components

*   **Frontend**: A React single-page application built with Vite and Tailwind CSS. It provides interfaces for document management, querying via an agentic chat interface, and visualizing the knowledge graph.
*   **Backend**: A FastAPI application that serves as the API gateway, handles document ingestion, and orchestrates the query agent.
*   **Asynchronous Pipeline**: A Celery-based worker queue backed by Redis that handles long-running tasks like document chunking, embedding generation, and graph entity extraction.
*   **Vector Database (Qdrant)**: Stores document embeddings for semantic similarity search.
*   **Graph Database (Neo4j)**: Stores extracted entities and their relationships, enabling multi-hop traversal and complex reasoning.
*   **Relational Database (PostgreSQL)**: Manages structured application state, tenant information, and document metadata.

### Backend Structure

*   **app/agent/**: Contains the core agentic routing logic. It evaluates user queries and decides whether to fetch context from the vector database, the graph database, or a hybrid of both.
*   **app/pipeline/**: Manages the data ingestion workflow. Documents are parsed, chunked, and sent through LLM pipelines to extract entities and generate embeddings asynchronously using Celery.
*   **app/core/**: Houses application configuration, database connection management, and security utilities.
*   **app/main.py**: The FastAPI entry point, defining the API routes for uploading documents, querying the agent, and fetching graph data for visualization.

### Frontend Structure

*   **src/components/ChatInterface.jsx**: The primary user interface for interacting with the GraphRAG agent.
*   **src/components/DocumentManager.jsx**: Handles uploading documents (PDFs, Markdown, CSVs) to expand the knowledge base.
*   **src/components/GraphCanvas.jsx**: Renders a 2D interactive force-directed graph of the extracted entities and their relationships.

## Prerequisites

*   Docker and Docker Compose
*   Node.js (for local frontend development)
*   Python 3.10+ (for local backend development)
*   An OpenAI API Key

## Getting Started

1.  **Clone the repository** and navigate to the project root.

2.  **Environment Setup**:
    Create a `.env` file based on `.env.example` in the root directory and fill in your configuration, specifically your `OPENAI_API_KEY`.

3.  **Start the Services**:
    Run the complete stack using Docker Compose:
    ```bash
    docker-compose up --build
    ```
    This command initializes PostgreSQL, Neo4j, Qdrant, Redis, the Celery worker, and the FastAPI backend.

4.  **Run the Frontend** (Local Development):
    In a separate terminal, navigate to the `frontend` directory:
    ```bash
    cd frontend
    npm install
    npm run dev
    ```

5.  **Access the Application**:
    Open your browser and navigate to the URL provided by the Vite development server (typically `http://localhost:5173`). The backend API is available at `http://localhost:8000`.
