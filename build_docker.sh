#!/bin/bash
# Build Nancy Brain MCP Server Docker Image with Embeddings
set -e

echo "🔨 Building Nancy Brain MCP Server Docker Image"
echo "================================================"

# Configuration
IMAGE_NAME="${NANCY_MCP_IMAGE:-nancy-brain-mcp}"
IMAGE_TAG="${NANCY_MCP_TAG:-latest}"

# Step 1: Build embeddings locally (if not already built)
if [ ! -d "knowledge_base/embeddings" ] || [ -z "$(ls -A knowledge_base/embeddings)" ]; then
    echo "📦 Building embeddings locally first..."
    python -m nancy_brain.cli build config/repositories.yml knowledge_base
else
    echo "✅ Embeddings already exist, skipping build"
fi

# Step 2: Build Docker image
echo "🐳 Building Docker image: ${IMAGE_NAME}:${IMAGE_TAG}"
docker build -t "${IMAGE_NAME}:${IMAGE_TAG}" .

# Step 3: Copy embeddings into image (optional: can also mount as volume)
echo "📋 Embeddings will be mounted at runtime via volume or copied during deployment"

echo ""
echo "✅ Build complete!"
echo "   Image: ${IMAGE_NAME}:${IMAGE_TAG}"
echo ""
echo "To run the server:"
echo "  docker run -p 8000:8000 \\"
echo "    -e MCP_API_KEY=your-secret-key \\"
echo "    -v $(pwd)/config:/app/config:ro \\"
echo "    -v $(pwd)/knowledge_base:/app/knowledge_base \\"
echo "    ${IMAGE_NAME}:${IMAGE_TAG}"
