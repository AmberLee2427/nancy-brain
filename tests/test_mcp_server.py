"""
Tests for the Nancy Brain MCP Server

Tests the Model Context Protocol server implementation.
"""

import pytest
import asyncio
from unittest.mock import Mock, AsyncMock, patch
from pathlib import Path

from connectors.mcp_server.server import NancyMCPServer


@pytest.fixture
def mock_rag_service():
    """Create a mock RAG service for testing."""
    mock = Mock()

    # Mock async methods
    async def mock_search_docs(query, limit=6, toolkit=None, doctype=None, threshold=0.0):
        return [
            {
                "id": "microlensing_tools/MulensModel/README.md",
                "text": "MulensModel is a Python package for gravitational microlensing modeling.",
                "score": 0.85,
            }
        ]

    async def mock_retrieve(doc_id, start=None, end=None):
        return {
            "doc_id": doc_id,
            "text": "Sample document content\nLine 2\nLine 3",
            "github_url": "https://github.com/rpoleski/MulensModel",
        }

    async def mock_retrieve_batch(items):
        results = []
        for item in items:
            result = await mock_retrieve(item["doc_id"], item.get("start"), item.get("end"))
            results.append(result)
        return results

    async def mock_list_tree(path="", max_depth=3):
        return [
            {
                "name": "microlensing_tools",
                "type": "directory",
                "children": [
                    {
                        "name": "MulensModel",
                        "type": "directory",
                        "children": [
                            {"name": "README.md", "type": "file"},
                            {"name": "setup.py", "type": "file"},
                        ],
                    }
                ],
            }
        ]

    async def mock_set_weight(doc_id, multiplier, namespace="global", ttl_days=None):
        return True

    async def mock_health():
        return {"status": "ok"}

    async def mock_version():
        return {
            "index_version": "test-1.0",
            "build_sha": "abc123",
            "built_at": "2025-08-23T12:00:00Z",
        }

    mock.search_docs = mock_search_docs
    mock.retrieve = mock_retrieve
    mock.retrieve_batch = mock_retrieve_batch
    mock.list_tree = mock_list_tree
    mock.set_weight = mock_set_weight
    mock.health = mock_health
    mock.version = mock_version

    return mock


@pytest.mark.asyncio
async def test_mcp_server_search_tool(mock_rag_service):
    """Test the search_knowledge_base tool."""
    server = NancyMCPServer()
    server.rag_service = mock_rag_service

    # Test search
    args = {"query": "microlensing modeling"}
    result = await server._handle_search(args)

    assert len(result) == 1
    assert result[0].type == "text"
    assert "microlensing_tools/MulensModel/README.md" in result[0].text
    assert "score: 0.850" in result[0].text


@pytest.mark.asyncio
async def test_mcp_server_retrieve_tool(mock_rag_service):
    """Test the retrieve_document_passage tool."""
    server = NancyMCPServer()
    server.rag_service = mock_rag_service

    # Test retrieve
    args = {"doc_id": "microlensing_tools/MulensModel/README.md", "start": 0, "end": 10}
    result = await server._handle_retrieve(args)

    assert len(result) == 1
    assert result[0].type == "text"
    assert "microlensing_tools/MulensModel/README.md" in result[0].text
    assert "Sample document content" in result[0].text


@pytest.mark.asyncio
async def test_mcp_server_retrieve_batch_tool(mock_rag_service):
    """Test the retrieve_multiple_passages tool."""
    server = NancyMCPServer()
    server.rag_service = mock_rag_service

    # Test batch retrieve
    args = {
        "items": [
            {"doc_id": "doc1.md", "start": 0, "end": 5},
            {"doc_id": "doc2.md", "start": 10, "end": 15},
        ]
    }
    result = await server._handle_retrieve_batch(args)

    assert len(result) == 1
    assert result[0].type == "text"
    assert "Retrieved 2 passages" in result[0].text


@pytest.mark.asyncio
async def test_mcp_server_tree_tool(mock_rag_service):
    """Test the explore_document_tree tool."""
    server = NancyMCPServer()
    server.rag_service = mock_rag_service

    # Test tree exploration
    args = {"path": "microlensing_tools", "max_depth": 2}
    result = await server._handle_tree(args)

    assert len(result) == 1
    assert result[0].type == "text"
    assert "Document Tree" in result[0].text
    assert "📁 microlensing_tools" in result[0].text
    assert "📄 README.md" in result[0].text


@pytest.mark.asyncio
async def test_mcp_server_weights_tool(mock_rag_service):
    """Test the set_retrieval_weights tool."""
    server = NancyMCPServer()
    server.rag_service = mock_rag_service

    # Test weight setting
    args = {
        "doc_id": "microlensing_tools/MulensModel/README.md",
        "weight": 1.5,
        "namespace": "global",
    }
    result = await server._handle_set_weights(args)

    assert len(result) == 1
    assert result[0].type == "text"
    assert "Weight Updated" in result[0].text
    assert "microlensing_tools/MulensModel/README.md" in result[0].text
    assert "1.5" in result[0].text


@pytest.mark.asyncio
async def test_mcp_server_status_tool(mock_rag_service):
    """Test the get_system_status tool."""
    server = NancyMCPServer()
    server.rag_service = mock_rag_service

    # Test status
    args = {}
    result = await server._handle_status(args)

    assert len(result) == 1
    assert result[0].type == "text"
    assert "Nancy Brain System Status" in result[0].text
    assert "✅" in result[0].text  # Health OK
    assert "test-1.0" in result[0].text  # Version


@pytest.mark.asyncio
async def test_mcp_server_no_service():
    """Test tool calls when RAG service is not initialized."""
    server = NancyMCPServer()
    # Don't set rag_service (it should be None)

    # Test search with no service
    args = {"query": "test"}
    result = await server._handle_search(args)

    assert len(result) == 1
    assert result[0].type == "text"
    assert "not initialized" in result[0].text or "Error executing" in result[0].text


def test_mcp_server_creation():
    """Test MCP server can be created."""
    server = NancyMCPServer()
    assert server.server is not None
    assert server.rag_service is None


@pytest.mark.asyncio
async def test_mcp_server_initialization():
    """Test MCP server initialization with mocked RAG service."""
    with patch("connectors.mcp_server.server.RAGService") as mock_rag_class:
        mock_rag = Mock()
        mock_rag_class.return_value = mock_rag

        server = NancyMCPServer()

        # Create temporary paths
        import tempfile

        with tempfile.TemporaryDirectory() as tmp_dir:
            config_path = Path(tmp_dir) / "config.yml"
            embeddings_path = Path(tmp_dir) / "embeddings"
            weights_path = Path(tmp_dir) / "weights.yml"

            config_path.write_text("test: config")
            embeddings_path.mkdir()
            weights_path.write_text("test: weights")

            await server.initialize(config_path, embeddings_path, weights_path)

            assert server.rag_service is not None
            mock_rag_class.assert_called_once_with(
                config_path=config_path,
                embeddings_path=embeddings_path,
                weights_path=weights_path,
            )
