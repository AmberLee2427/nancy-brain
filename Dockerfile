# Nancy Brain MCP Server Docker Image
# Includes knowledge base embeddings build and HTTP API with authentication

FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    git \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy project files
COPY pyproject.toml ./
COPY README.md ./
COPY nancy_brain ./nancy_brain
COPY rag_core ./rag_core
COPY connectors ./connectors
COPY scripts ./scripts
COPY hatch_hooks.py ./
COPY run_mcp_server.py ./

# Install Python dependencies
RUN pip install --no-cache-dir -e .

# Create directories for config and data
RUN mkdir -p /app/config /app/knowledge_base/embeddings /app/cache

# Environment variables (override at runtime)
ENV MCP_PORT=8000
ENV NB_SECRET_KEY=""
ENV NB_ALLOW_INSECURE="false"
ENV PYTHONUNBUFFERED=1
ENV KMP_DUPLICATE_LIB_OK=TRUE

# Expose HTTP port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD python -c "import requests; requests.get('http://localhost:8000/health').raise_for_status()" || exit 1

# Run MCP server in HTTP mode
CMD ["python", "run_mcp_server.py"]
