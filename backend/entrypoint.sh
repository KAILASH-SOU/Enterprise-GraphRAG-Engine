#!/bin/bash
# Entrypoint script for running multiple services

set -e

# Function to wait for service
wait_for_service() {
    local host=$1
    local port=$2
    local service=$3
    echo "Waiting for $service at $host:$port..."
    while ! nc -z $host $port; do
        sleep 1
    done
    echo "$service is ready!"
}

# Wait for dependencies
wait_for_service postgres 5432 "PostgreSQL"
wait_for_service neo4j 7687 "Neo4j"
wait_for_service qdrant 6333 "Qdrant"
wait_for_service redis 6379 "Redis"

# Run database migrations if needed
# python -m alembic upgrade head

# Start the requested service
case "$1" in
    "api")
        exec uvicorn app.main:app --host 0.0.0.0 --port 8000
        ;;
    "worker")
        exec celery -A app.pipeline.tasks.celery_app worker --loglevel=info --concurrency=2
        ;;
    "beat")
        exec celery -A app.pipeline.tasks.celery_app beat --loglevel=info
        ;;
    "streamlit")
        exec streamlit run ../frontend/streamlit_app.py --server.port=8501 --server.address=0.0.0.0
        ;;
    *)
        echo "Usage: $0 {api|worker|beat|streamlit}"
        exit 1
        ;;
esac