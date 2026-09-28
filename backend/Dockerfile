FROM python:3.11-slim

WORKDIR /app

# Install system dependencies for igraph
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libc-dev \
    libigraph0v5 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Expose both FastAPI and Streamlit ports
EXPOSE 8000 8501

# Default to FastAPI, can be overridden
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]