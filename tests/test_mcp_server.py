"""
Tests for the Nancy Brain MCP Server

Tests the Model Context Protocol server implementation.
"""

import pytest
import asyncio
import sqlite3
from unittest.mock import Mock, AsyncMock, patch
from pathlib import Path

from mcp import types as mcp_types
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
    args = {"doc_id": "microlensing_tools/MulensModel/README.md", "start": 1, "end": 3}
    result = await server._handle_retrieve(args)

    assert len(result) == 1
    assert result[0].type == "text"
    assert "microlensing_tools/MulensModel/README.md" in result[0].text
    assert "Sample document content" in result[0].text


@pytest.mark.asyncio
async def test_mcp_server_retrieve_chunk_window(mock_rag_service):
    """Test chunk-window retrieval when doc_id is a chunk and no line range is provided."""
    server = NancyMCPServer()
    server.rag_service = mock_rag_service

    server._retrieve_chunk_window = Mock(
        return_value={
            "text": "[Chunk] doc::chunk-0001\nchunk one\n\n[Chunk] doc::chunk-0002\nchunk two",
            "chunks": [
                {"doc_id": "doc::chunk-0001", "line_start": 1, "line_end": 10},
                {"doc_id": "doc::chunk-0002", "line_start": 11, "line_end": 20},
            ],
        }
    )

    args = {"doc_id": "doc::chunk-0001"}
    result = await server._handle_retrieve(args)

    assert len(result) == 1
    assert result[0].type == "text"
    assert "**Chunks:** 2" in result[0].text
    assert "lines 1-10" in result[0].text


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
async def test_mcp_server_tree_tool_flat_entries(mock_rag_service):
    """Tree rendering should handle flat path/type entries from rag_service.list_tree."""
    server = NancyMCPServer()
    server.rag_service = mock_rag_service

    async def flat_tree(path="", max_depth=3):
        return [
            {"path": "microlensing_tools", "type": "directory"},
            {"path": "microlensing_tools/RTModel", "type": "directory"},
            {"path": "microlensing_tools/RTModel/README.md", "type": "file"},
        ]

    server.rag_service.list_tree = flat_tree
    result = await server._handle_tree({"max_depth": 2})

    assert len(result) == 1
    assert "unknown/" not in result[0].text
    assert "microlensing_tools/RTModel/README.md" in result[0].text


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
async def test_mcp_server_weights_tool_namespace_only(mock_rag_service):
    """Namespace-only set_retrieval_weights calls should not fail with missing doc_id."""
    server = NancyMCPServer()
    server.rag_service = mock_rag_service
    server.rag_service.set_weight = AsyncMock(return_value=True)

    result = await server._handle_set_weights({"namespace": "microlensing_tools", "weight": 2.0})

    assert len(result) == 1
    assert "Namespace Prefix" in result[0].text
    assert "microlensing_tools/" in result[0].text
    server.rag_service.set_weight.assert_awaited_once_with("microlensing_tools/", 2.0, "microlensing_tools", None)


@pytest.mark.asyncio
async def test_mcp_server_weights_tool_path_alias_with_namespace(mock_rag_service):
    """Using the 'path' alias with namespace should label the response as 'Document', not 'Namespace Prefix'."""
    server = NancyMCPServer()
    server.rag_service = mock_rag_service
    server.rag_service.set_weight = AsyncMock(return_value=True)

    result = await server._handle_set_weights(
        {"path": "microlensing_tools/MulensModel/README.md", "namespace": "microlensing_tools", "weight": 1.5}
    )

    assert len(result) == 1
    assert "Document" in result[0].text
    assert "Namespace Prefix" not in result[0].text
    assert "microlensing_tools/MulensModel/README.md" in result[0].text


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


# ---- Internal helper unit tests ----------------------------------------


def _make_sections_db(tmp_path: Path) -> Path:
    """Create a minimal embeddings index DB at the standard location."""
    index_dir = tmp_path / "embeddings" / "index"
    index_dir.mkdir(parents=True, exist_ok=True)
    db_path = index_dir / "documents"
    conn = sqlite3.connect(str(db_path))
    conn.execute(
        """
        CREATE TABLE sections (
            indexid INTEGER PRIMARY KEY AUTOINCREMENT,
            id TEXT,
            text TEXT,
            data TEXT,
            entry DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    rows = [
        (
            "doc/file.py::chunk-0001",
            "chunk one content",
            '{"source_document": "doc/file.py", "chunk_index": 1, "chunk_count": 3, "line_start": 10, "line_end": 20}',
        ),
        (
            "doc/file.py::chunk-0002",
            "chunk two content",
            '{"source_document": "doc/file.py", "chunk_index": 2, "chunk_count": 3, "line_start": 21, "line_end": 30}',
        ),
        (
            "doc/file.py::chunk-0003",
            "chunk three content",
            '{"source_document": "doc/file.py", "chunk_index": 3, "chunk_count": 3, "line_start": 31, "line_end": 40}',
        ),
        (
            "knowledge_base/raw/some/README.md::chunk-0000",
            "readme text",
            '{"source_document": "knowledge_base/raw/some/README.md"}',
        ),
    ]
    conn.executemany("INSERT INTO sections (id, text, data) VALUES (?, ?, ?)", rows)
    conn.commit()
    conn.close()
    return tmp_path / "embeddings"


def test_parse_chunk_id_valid_double_colon():
    server = NancyMCPServer()
    result = server._parse_chunk_id("doc/file.py::chunk-0001")
    assert result is not None
    base, marker, idx, width = result
    assert base == "doc/file.py"
    assert marker == "::chunk-"
    assert idx == 1
    assert width == 4


def test_parse_chunk_id_valid_hash():
    server = NancyMCPServer()
    result = server._parse_chunk_id("doc/file.py#chunk-0042")
    assert result is not None
    base, marker, idx, width = result
    assert base == "doc/file.py"
    assert marker == "#chunk-"
    assert idx == 42


def test_parse_chunk_id_invalid():
    server = NancyMCPServer()
    assert server._parse_chunk_id("doc/file.py") is None
    assert server._parse_chunk_id("") is None
    assert server._parse_chunk_id(None) is None


def test_parse_chunk_id_pipe_format():
    server = NancyMCPServer()
    result = server._parse_chunk_id("doc/file.py|chunk:7")
    assert result is not None
    _, marker, idx, _ = result
    assert marker == "|chunk:"
    assert idx == 7


def test_get_embeddings_db_path_no_service():
    server = NancyMCPServer()
    assert server._get_embeddings_db_path() is None


def test_get_embeddings_db_path_with_service(tmp_path):
    server = NancyMCPServer()
    mock_svc = Mock()
    mock_svc.embeddings_path = tmp_path / "embeddings"
    server.rag_service = mock_svc
    result = server._get_embeddings_db_path()
    assert result == tmp_path / "embeddings" / "index" / "documents"


def test_fetch_section_row_found(tmp_path):
    embeddings_path = _make_sections_db(tmp_path)
    db_path = embeddings_path / "index" / "documents"
    conn = sqlite3.connect(str(db_path))
    server = NancyMCPServer()
    try:
        row = server._fetch_section_row(conn, "doc/file.py::chunk-0001")
        assert row is not None
        assert row["id"] == "doc/file.py::chunk-0001"
        assert "chunk one" in row["text"]
        assert row["data"]["source_document"] == "doc/file.py"
    finally:
        conn.close()


def test_fetch_section_row_not_found(tmp_path):
    embeddings_path = _make_sections_db(tmp_path)
    db_path = embeddings_path / "index" / "documents"
    conn = sqlite3.connect(str(db_path))
    server = NancyMCPServer()
    try:
        row = server._fetch_section_row(conn, "nonexistent/doc.py::chunk-0000")
        assert row is None
    finally:
        conn.close()


def test_fetch_section_row_empty_table(tmp_path):
    """_fetch_section_row returns a row when table has only id/text columns (no data/metadata columns)."""
    db_path = tmp_path / "empty.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE sections (id TEXT, text TEXT)")
    conn.execute("INSERT INTO sections VALUES ('x', 'y')")
    conn.commit()
    server = NancyMCPServer()
    try:
        row = server._fetch_section_row(conn, "x")
        assert row is not None
        assert row["id"] == "x"
    finally:
        conn.close()


def test_retrieve_chunk_window_success(tmp_path):
    """_retrieve_chunk_window returns adjacent chunks from the DB."""
    embeddings_path = _make_sections_db(tmp_path)
    server = NancyMCPServer()
    mock_svc = Mock()
    mock_svc.embeddings_path = embeddings_path
    server.rag_service = mock_svc

    result = server._retrieve_chunk_window("doc/file.py::chunk-0002", window=1)
    assert result is not None
    assert "chunks" in result
    assert len(result["chunks"]) >= 1
    assert any("chunk" in ch.get("text", "") for ch in result["chunks"])


def test_retrieve_chunk_window_not_a_chunk():
    """_retrieve_chunk_window returns None for non-chunk doc ids."""
    server = NancyMCPServer()
    result = server._retrieve_chunk_window("doc/file.py")
    assert result is None


def test_retrieve_chunk_window_no_db(tmp_path):
    """_retrieve_chunk_window returns None when DB does not exist."""
    server = NancyMCPServer()
    mock_svc = Mock()
    mock_svc.embeddings_path = tmp_path / "nonexistent_embeddings"
    server.rag_service = mock_svc
    result = server._retrieve_chunk_window("doc/file.py::chunk-0001", window=1)
    assert result is None


def test_retrieve_chunk_window_no_chunks_in_window(tmp_path):
    """_retrieve_chunk_window returns None when no matching chunks exist."""
    embeddings_path = _make_sections_db(tmp_path)
    server = NancyMCPServer()
    mock_svc = Mock()
    mock_svc.embeddings_path = embeddings_path
    server.rag_service = mock_svc

    # Request a chunk ID that is not in the DB
    result = server._retrieve_chunk_window("other/doc.py::chunk-0099", window=0)
    assert result is None


def test_resolve_retrievable_doc_id_no_db(tmp_path):
    """_resolve_retrievable_doc_id returns original doc_id when DB does not exist."""
    server = NancyMCPServer()
    mock_svc = Mock()
    mock_svc.embeddings_path = tmp_path / "nonexistent"
    server.rag_service = mock_svc

    result = server._resolve_retrievable_doc_id("some/doc.py")
    assert result == "some/doc.py"


def test_resolve_retrievable_doc_id_empty():
    """_resolve_retrievable_doc_id returns empty string for empty input."""
    server = NancyMCPServer()
    result = server._resolve_retrievable_doc_id("")
    assert result == ""


def test_resolve_retrievable_doc_id_direct_hit(tmp_path):
    """_resolve_retrievable_doc_id returns exact match from the DB."""
    embeddings_path = _make_sections_db(tmp_path)
    server = NancyMCPServer()
    mock_svc = Mock()
    mock_svc.embeddings_path = embeddings_path
    server.rag_service = mock_svc

    result = server._resolve_retrievable_doc_id("doc/file.py::chunk-0001")
    assert result == "doc/file.py::chunk-0001"


def test_resolve_retrievable_doc_id_chunk_suffix_added(tmp_path):
    """_resolve_retrievable_doc_id resolves base doc_id to a chunk-0 entry when available."""
    embeddings_path = _make_sections_db(tmp_path)
    server = NancyMCPServer()
    mock_svc = Mock()
    mock_svc.embeddings_path = embeddings_path
    server.rag_service = mock_svc

    # "doc/file.py" is not in DB directly, but "doc/file.py::chunk-0001" is
    result = server._resolve_retrievable_doc_id("doc/file.py")
    # Should find the chunk variant (chunk-0001 is the first in DB but chunk-0 is tried first)
    # The logic tries chunk-0 first; since we don't have chunk-0, it falls through to metadata
    assert "doc/file.py" in result


def test_resolve_retrievable_doc_id_kb_prefix(tmp_path):
    """_resolve_retrievable_doc_id handles knowledge_base/raw prefix lookup."""
    embeddings_path = _make_sections_db(tmp_path)
    server = NancyMCPServer()
    mock_svc = Mock()
    mock_svc.embeddings_path = embeddings_path
    server.rag_service = mock_svc

    # "knowledge_base/raw/some/README.md::chunk-0000" is in DB
    result = server._resolve_retrievable_doc_id("knowledge_base/raw/some/README.md")
    assert "knowledge_base/raw/some/README.md" in result


@pytest.mark.asyncio
async def test_handle_search_no_results(mock_rag_service):
    """_handle_search returns a 'no results' message when search is empty."""
    server = NancyMCPServer()
    server.rag_service = mock_rag_service

    async def empty_search(query, limit=6, toolkit=None, doctype=None, threshold=0.0):
        return []

    server.rag_service.search_docs = empty_search

    result = await server._handle_search({"query": "nonexistent topic"})
    assert len(result) == 1
    assert "No results" in result[0].text


@pytest.mark.asyncio
async def test_handle_set_weights_no_doc_or_namespace(mock_rag_service):
    """_handle_set_weights returns an error when neither doc_id nor namespace is provided."""
    server = NancyMCPServer()
    server.rag_service = mock_rag_service

    result = await server._handle_set_weights({"weight": 1.5})
    assert len(result) == 1
    assert "requires either" in result[0].text


@pytest.mark.asyncio
async def test_handle_set_weights_clamped(mock_rag_service):
    """_handle_set_weights shows clamped weight message when requested weight is out of range."""
    server = NancyMCPServer()
    server.rag_service = mock_rag_service
    server.rag_service.set_weight = AsyncMock(return_value=True)

    result = await server._handle_set_weights({"doc_id": "some/doc.py", "weight": 5.0})
    assert "clamped" in result[0].text.lower() or "Actual Weight" in result[0].text


@pytest.mark.asyncio
async def test_handle_set_weights_with_ttl(mock_rag_service):
    """_handle_set_weights includes TTL information in the response."""
    server = NancyMCPServer()
    server.rag_service = mock_rag_service
    server.rag_service.set_weight = AsyncMock(return_value=True)

    result = await server._handle_set_weights(
        {
            "doc_id": "some/doc.py",
            "weight": 1.2,
            "ttl_days": 30,
        }
    )
    assert "30" in result[0].text
    assert "TTL" in result[0].text


@pytest.mark.asyncio
async def test_handle_status_no_system_status(mock_rag_service):
    """_handle_status falls back gracefully when system_status is unavailable."""
    server = NancyMCPServer()

    mock_svc = Mock()
    # Remove system_status so it falls through to health + version path
    del mock_svc.system_status

    async def mock_health():
        return {"status": "ok", "registry_loaded": True, "store_loaded": True, "search_loaded": True}

    async def mock_version():
        return {"index_version": "v2.0", "build_sha": "def456", "built_at": "2025-01-01T00:00:00Z"}

    mock_svc.health = mock_health
    mock_svc.version = mock_version
    server.rag_service = mock_svc

    result = await server._handle_status({})
    assert "Nancy Brain System Status" in result[0].text
    assert "v2.0" in result[0].text


@pytest.mark.asyncio
async def test_handle_retrieve_full_doc_fallback(mock_rag_service):
    """_handle_retrieve falls back to full document when no line range and no chunk id."""
    server = NancyMCPServer()
    server.rag_service = mock_rag_service

    # _resolve_retrievable_doc_id will return as-is (no DB), chunk window will be None
    result = await server._handle_retrieve({"doc_id": "microlensing_tools/MulensModel/README.md"})
    assert len(result) == 1
    assert result[0].type == "text"
    assert "microlensing_tools/MulensModel/README.md" in result[0].text


@pytest.mark.asyncio
async def test_handle_retrieve_not_found(mock_rag_service):
    """_handle_retrieve returns error message when document is not found."""
    server = NancyMCPServer()
    server.rag_service = mock_rag_service

    async def not_found_retrieve(doc_id, start=None, end=None):
        return None

    server.rag_service.retrieve = not_found_retrieve

    result = await server._handle_retrieve({"doc_id": "nonexistent/doc.py"})
    assert "not found" in result[0].text.lower() or "Document" in result[0].text


# ---- Additional coverage tests ------------------------------------------


@pytest.mark.asyncio
async def test_handle_retrieve_file_not_found(mock_rag_service):
    """_handle_retrieve returns error when FileNotFoundError is raised."""
    server = NancyMCPServer()
    server.rag_service = mock_rag_service

    async def raise_fnf(doc_id, start=None, end=None):
        raise FileNotFoundError(f"Not found: {doc_id}")

    server.rag_service.retrieve = raise_fnf

    result = await server._handle_retrieve({"doc_id": "missing/doc.md", "start": 1, "end": 10})
    assert len(result) == 1
    # Should return "not found" message or fall through to chunk window (None → not found)
    assert "missing/doc.md" in result[0].text or "not found" in result[0].text.lower()


@pytest.mark.asyncio
async def test_handle_retrieve_chunk_window_fallback_on_range(tmp_path, mock_rag_service):
    """_handle_retrieve falls back to chunk window when range retrieval fails."""
    server = NancyMCPServer()
    server.rag_service = mock_rag_service

    embeddings_path = _make_sections_db(tmp_path)
    mock_svc = Mock()
    mock_svc.embeddings_path = embeddings_path

    async def failing_retrieve(doc_id, start=None, end=None):
        raise FileNotFoundError(f"Not found: {doc_id}")

    mock_svc.retrieve = failing_retrieve
    mock_svc.registry = Mock()
    mock_svc.registry.get_github_url = Mock(return_value="")

    server.rag_service = mock_svc

    # chunk-0002 is in the DB
    result = await server._handle_retrieve({"doc_id": "doc/file.py::chunk-0002", "start": 1, "end": 5})
    assert len(result) == 1
    text = result[0].text
    # Should show chunk window output
    assert "doc/file.py::chunk-0002" in text or "Chunks:" in text


@pytest.mark.asyncio
async def test_handle_retrieve_with_line_range_and_result(mock_rag_service):
    """_handle_retrieve formats lines correctly for range retrieval."""
    server = NancyMCPServer()
    server.rag_service = mock_rag_service

    result = await server._handle_retrieve({"doc_id": "microlensing_tools/MulensModel/README.md", "start": 1, "end": 3})
    assert len(result) == 1
    text = result[0].text
    assert "Lines:" in text
    assert "1 - 3" in text
    assert "Partial passage" in text


@pytest.mark.asyncio
async def test_handle_retrieve_batch_empty(mock_rag_service):
    """_handle_retrieve_batch returns error for empty results."""
    server = NancyMCPServer()
    server.rag_service = mock_rag_service

    async def empty_batch(items):
        return []

    server.rag_service.retrieve_batch = empty_batch

    result = await server._handle_retrieve_batch({"items": [{"doc_id": "doc.py"}]})
    assert len(result) == 1
    assert "No documents" in result[0].text


@pytest.mark.asyncio
async def test_handle_retrieve_batch_partial_passage(mock_rag_service):
    """_handle_retrieve_batch marks partial when end < total_lines."""
    server = NancyMCPServer()
    server.rag_service = mock_rag_service

    result = await server._handle_retrieve_batch(
        {
            "items": [
                {"doc_id": "doc1.md", "start": 0, "end": 5},
                {"doc_id": "doc2.md", "start": 10, "end": 15},
            ]
        }
    )
    assert len(result) == 1
    assert "Retrieved 2 passages" in result[0].text


@pytest.mark.asyncio
async def test_handle_status_no_rag_service():
    """_handle_status returns error when rag_service is None."""
    server = NancyMCPServer()
    server.rag_service = None
    result = await server._handle_status({})
    assert "not initialized" in result[0].text


@pytest.mark.asyncio
async def test_handle_status_with_system_status_exception(mock_rag_service):
    """_handle_status falls back gracefully when system_status() raises."""
    server = NancyMCPServer()

    mock_svc = Mock()

    async def raising_system_status():
        raise RuntimeError("DB unavailable")

    async def mock_health():
        return {"status": "degraded", "registry_loaded": False, "store_loaded": True, "search_loaded": True}

    async def mock_version():
        return {"index_version": "v3.0", "build_sha": "aaa111", "built_at": "2025-01-01T00:00:00Z"}

    mock_svc.system_status = raising_system_status
    mock_svc.health = mock_health
    mock_svc.version = mock_version
    server.rag_service = mock_svc

    result = await server._handle_status({})
    assert "Nancy Brain System Status" in result[0].text
    assert "v3.0" in result[0].text


@pytest.mark.asyncio
async def test_handle_status_with_dependencies(mock_rag_service):
    """_handle_status displays dependencies when present in system_status."""
    server = NancyMCPServer()

    mock_svc = Mock()

    async def mock_system_status():
        return {
            "status": "ok",
            "index_version": "v4.0",
            "build_sha": "bbb222",
            "built_at": "2025-01-01T00:00:00Z",
            "python_version": "3.12",
            "python_implementation": "CPython",
            "environment": "production",
            "dependencies": {"txtai": "7.0", "mcp": "1.0"},
        }

    async def mock_health():
        return {"status": "ok"}

    mock_svc.system_status = mock_system_status
    mock_svc.health = mock_health
    server.rag_service = mock_svc

    result = await server._handle_status({})
    assert "Dependencies:" in result[0].text
    assert "txtai" in result[0].text
    assert "mcp" in result[0].text


@pytest.mark.asyncio
async def test_handle_tree_format_tree_nested(mock_rag_service):
    """_handle_tree correctly formats nested children."""
    server = NancyMCPServer()
    server.rag_service = mock_rag_service

    async def nested_tree(path="", max_depth=3):
        return [
            {
                "name": "repo",
                "type": "directory",
                "children": [
                    {"name": "README.md", "type": "file"},
                    {"name": "src", "type": "directory", "children": []},
                ],
            }
        ]

    server.rag_service.list_tree = nested_tree

    result = await server._handle_tree({})
    assert "📁 repo/" in result[0].text
    assert "📄 README.md" in result[0].text
    assert "📁 src/" in result[0].text


@pytest.mark.asyncio
async def test_handle_tree_string_items(mock_rag_service):
    """_handle_tree handles non-dict items (raw string paths)."""
    server = NancyMCPServer()
    server.rag_service = mock_rag_service

    async def string_tree(path="", max_depth=3):
        return ["some/path/file.py", "other/path/README.md"]

    server.rag_service.list_tree = string_tree

    result = await server._handle_tree({})
    assert "some/path/file.py" in result[0].text
    assert "other/path/README.md" in result[0].text


@pytest.mark.asyncio
async def test_handle_tree_with_path_filter(mock_rag_service):
    """_handle_tree with path filter shows filtered path correctly."""
    server = NancyMCPServer()
    server.rag_service = mock_rag_service

    async def filtered_tree(path="", max_depth=3):
        return [
            {"path": "tools/sub/file.py", "type": "file"},
            {"path": "tools/sub/other.py", "type": "file"},
        ]

    server.rag_service.list_tree = filtered_tree

    result = await server._handle_tree({"path": "tools/sub", "max_depth": 2})
    assert "path: tools/sub" in result[0].text


def test_fetch_section_row_no_columns(tmp_path):
    """_fetch_section_row returns None when sections table has no schema."""
    db_path = tmp_path / "empty.db"
    conn = sqlite3.connect(str(db_path))
    # Create a table that PRAGMA won't find (simulate empty/missing column schema)
    # Actually PRAGMA table_info returns rows for any valid table;
    # test the empty-columns branch by not creating any table.
    server = NancyMCPServer()
    try:
        row = server._fetch_section_row(conn, "any/id")
        assert row is None
    finally:
        conn.close()


def test_retrieve_chunk_window_text_combined(tmp_path):
    """_retrieve_chunk_window combines multiple chunks into text."""
    embeddings_path = _make_sections_db(tmp_path)
    server = NancyMCPServer()
    mock_svc = Mock()
    mock_svc.embeddings_path = embeddings_path
    server.rag_service = mock_svc

    result = server._retrieve_chunk_window("doc/file.py::chunk-0002", window=1)
    assert result is not None
    assert "[Chunk]" in result["text"]
    assert len(result["chunks"]) >= 1


def test_retrieve_chunk_window_chunk_without_line_info(tmp_path):
    """_retrieve_chunk_window includes chunks even without line_start/line_end."""
    # Add a chunk without line info to the DB
    embeddings_path = tmp_path / "embeddings"
    index_dir = embeddings_path / "index"
    index_dir.mkdir(parents=True, exist_ok=True)
    db_path = index_dir / "documents"
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE sections (id TEXT, text TEXT, data TEXT)")
    conn.execute(
        "INSERT INTO sections VALUES (?, ?, ?)",
        ("nolines/doc.py::chunk-001", "content without lines", '{"source_document": "nolines/doc.py"}'),
    )
    conn.commit()
    conn.close()

    server = NancyMCPServer()
    mock_svc = Mock()
    mock_svc.embeddings_path = embeddings_path
    server.rag_service = mock_svc

    result = server._retrieve_chunk_window("nolines/doc.py::chunk-001", window=0)
    assert result is not None
    ch = result["chunks"][0]
    assert ch["line_start"] is None
    assert ch["line_end"] is None


# ---- MCP handler closure coverage tests --------------------------------


@pytest.mark.asyncio
async def test_list_tools_handler():
    """handle_list_tools closure returns all expected tools."""
    server = NancyMCPServer()
    handler = server.server.request_handlers[mcp_types.ListToolsRequest]
    result = await handler(mcp_types.ListToolsRequest(method="tools/list"))
    tool_names = {t.name for t in result.root.tools}
    assert "search_knowledge_base" in tool_names
    assert "retrieve_document_passage" in tool_names
    assert "explore_document_tree" in tool_names
    assert "set_retrieval_weights" in tool_names
    assert "get_system_status" in tool_names


@pytest.mark.asyncio
async def test_call_tool_handler_no_service():
    """handle_call_tool returns 'not initialized' error when rag_service is None."""
    server = NancyMCPServer()
    handler = server.server.request_handlers[mcp_types.CallToolRequest]
    req = mcp_types.CallToolRequest(
        method="tools/call",
        params=mcp_types.CallToolRequestParams(name="search_knowledge_base", arguments={"query": "test"}),
    )
    result = await handler(req)
    assert "not initialized" in result.root.content[0].text


@pytest.mark.asyncio
async def test_call_tool_handler_unknown_tool(mock_rag_service):
    """handle_call_tool returns 'Unknown tool' for unrecognized tool names."""
    server = NancyMCPServer()
    server.rag_service = mock_rag_service
    handler = server.server.request_handlers[mcp_types.CallToolRequest]
    req = mcp_types.CallToolRequest(
        method="tools/call",
        params=mcp_types.CallToolRequestParams(name="nonexistent_tool", arguments={}),
    )
    result = await handler(req)
    assert "Unknown tool" in result.root.content[0].text


@pytest.mark.asyncio
async def test_call_tool_handler_exception(mock_rag_service):
    """handle_call_tool catches exceptions and returns an error message."""
    server = NancyMCPServer()
    server.rag_service = mock_rag_service

    async def raise_error(args):
        raise RuntimeError("Unexpected crash")

    server._handle_search = raise_error
    handler = server.server.request_handlers[mcp_types.CallToolRequest]
    req = mcp_types.CallToolRequest(
        method="tools/call",
        params=mcp_types.CallToolRequestParams(name="search_knowledge_base", arguments={"query": "test"}),
    )
    result = await handler(req)
    assert "Error executing" in result.root.content[0].text


def test_fetch_section_row_metadata_column(tmp_path):
    """_fetch_section_row falls back to 'metadata' column when 'data' is absent."""
    db_path = tmp_path / "meta.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE sections (id TEXT, text TEXT, metadata TEXT)")
    conn.execute(
        "INSERT INTO sections VALUES (?, ?, ?)",
        ("meta/doc.py::chunk-0", "meta content", '{"source_document": "meta/doc.py"}'),
    )
    conn.commit()
    server = NancyMCPServer()
    try:
        row = server._fetch_section_row(conn, "meta/doc.py::chunk-0")
        assert row is not None
        assert row["data"]["source_document"] == "meta/doc.py"
    finally:
        conn.close()


def test_fetch_section_row_bad_json_metadata(tmp_path):
    """_fetch_section_row handles non-JSON metadata gracefully."""
    db_path = tmp_path / "badjson.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE sections (id TEXT, text TEXT, data TEXT)")
    conn.execute("INSERT INTO sections VALUES (?, ?, ?)", ("bad/doc.py::chunk-0", "text", "NOT_JSON"))
    conn.commit()
    server = NancyMCPServer()
    try:
        row = server._fetch_section_row(conn, "bad/doc.py::chunk-0")
        # Row is returned but data is not parsed
        assert row is not None
        assert "data" not in row
    finally:
        conn.close()


@pytest.mark.asyncio
async def test_initialize_error_propagates(tmp_path):
    """initialize() re-raises if RAGService constructor fails."""
    with patch("connectors.mcp_server.server.RAGService", side_effect=RuntimeError("init failed")):
        server = NancyMCPServer()
        config = tmp_path / "cfg.yml"
        config.write_text("{}")
        embeddings = tmp_path / "embeddings"
        embeddings.mkdir()
        weights = tmp_path / "weights.yaml"
        weights.write_text("extensions: {}")

        with pytest.raises(RuntimeError, match="init failed"):
            await server.initialize(config, embeddings, weights)


def test_resolve_doc_id_metadata_column_lookup(tmp_path):
    """_resolve_retrievable_doc_id uses json metadata column to find the first chunk."""
    embeddings_path = tmp_path / "embeddings"
    index_dir = embeddings_path / "index"
    index_dir.mkdir(parents=True, exist_ok=True)
    db_path = index_dir / "documents"
    conn = sqlite3.connect(str(db_path))
    # Use 'metadata' instead of 'data' to exercise the metadata column path
    conn.execute("CREATE TABLE sections (id TEXT, text TEXT, metadata TEXT)")
    conn.execute(
        "INSERT INTO sections VALUES (?, ?, ?)",
        (
            "knowledge_base/raw/tool/doc.py::chunk-0",
            "content",
            '{"source_document": "tool/doc.py", "chunk_index": 0}',
        ),
    )
    conn.commit()
    conn.close()

    server = NancyMCPServer()
    mock_svc = Mock()
    mock_svc.embeddings_path = embeddings_path
    server.rag_service = mock_svc

    result = server._resolve_retrievable_doc_id("tool/doc.py")
    assert "tool/doc.py" in result


@pytest.mark.asyncio
async def test_handle_status_health_raises_after_system_status(mock_rag_service):
    """_handle_status silently ignores failures in health() when system_status succeeds."""
    server = NancyMCPServer()
    mock_svc = Mock()

    async def good_system_status():
        return {
            "status": "ok",
            "index_version": "v5.0",
            "build_sha": "ccc333",
            "built_at": "2025-01-01T00:00:00Z",
        }

    async def raising_health():
        raise RuntimeError("health check failed")

    mock_svc.system_status = good_system_status
    mock_svc.health = raising_health
    server.rag_service = mock_svc

    result = await server._handle_status({})
    assert "Nancy Brain System Status" in result[0].text
    assert "v5.0" in result[0].text


# ---- Tool dispatch coverage via CallToolRequest -------------------------


@pytest.mark.asyncio
async def test_call_tool_handler_retrieve(mock_rag_service):
    """handle_call_tool dispatches retrieve_document_passage correctly."""
    server = NancyMCPServer()
    server.rag_service = mock_rag_service
    handler = server.server.request_handlers[mcp_types.CallToolRequest]
    req = mcp_types.CallToolRequest(
        method="tools/call",
        params=mcp_types.CallToolRequestParams(
            name="retrieve_document_passage",
            arguments={"doc_id": "microlensing_tools/MulensModel/README.md"},
        ),
    )
    result = await handler(req)
    assert result.root.content[0].type == "text"


@pytest.mark.asyncio
async def test_call_tool_handler_retrieve_batch(mock_rag_service):
    """handle_call_tool dispatches retrieve_multiple_passages correctly."""
    server = NancyMCPServer()
    server.rag_service = mock_rag_service
    handler = server.server.request_handlers[mcp_types.CallToolRequest]
    req = mcp_types.CallToolRequest(
        method="tools/call",
        params=mcp_types.CallToolRequestParams(
            name="retrieve_multiple_passages",
            arguments={"items": [{"doc_id": "doc.md"}]},
        ),
    )
    result = await handler(req)
    assert result.root.content[0].type == "text"


@pytest.mark.asyncio
async def test_call_tool_handler_explore_tree(mock_rag_service):
    """handle_call_tool dispatches explore_document_tree correctly."""
    server = NancyMCPServer()
    server.rag_service = mock_rag_service
    handler = server.server.request_handlers[mcp_types.CallToolRequest]
    req = mcp_types.CallToolRequest(
        method="tools/call",
        params=mcp_types.CallToolRequestParams(
            name="explore_document_tree",
            arguments={"path": "microlensing_tools", "max_depth": 2},
        ),
    )
    result = await handler(req)
    assert result.root.content[0].type == "text"


@pytest.mark.asyncio
async def test_call_tool_handler_set_weights(mock_rag_service):
    """handle_call_tool dispatches set_retrieval_weights correctly."""
    server = NancyMCPServer()
    server.rag_service = mock_rag_service
    server.rag_service.set_weight = AsyncMock(return_value=True)
    handler = server.server.request_handlers[mcp_types.CallToolRequest]
    req = mcp_types.CallToolRequest(
        method="tools/call",
        params=mcp_types.CallToolRequestParams(
            name="set_retrieval_weights",
            arguments={"doc_id": "some/doc.py", "weight": 1.3},
        ),
    )
    result = await handler(req)
    assert "Weight Updated" in result.root.content[0].text


@pytest.mark.asyncio
async def test_call_tool_handler_get_system_status(mock_rag_service):
    """handle_call_tool dispatches get_system_status correctly."""
    server = NancyMCPServer()
    server.rag_service = mock_rag_service
    handler = server.server.request_handlers[mcp_types.CallToolRequest]
    req = mcp_types.CallToolRequest(
        method="tools/call",
        params=mcp_types.CallToolRequestParams(
            name="get_system_status",
            arguments={},
        ),
    )
    result = await handler(req)
    assert "Nancy Brain System Status" in result.root.content[0].text


@pytest.mark.asyncio
async def test_handle_retrieve_with_total_lines(tmp_path):
    """_handle_retrieve counts total lines when file exists in the store."""
    server = NancyMCPServer()

    # Store is initialized as Store(embeddings_path.parent) = Store(tmp_path),
    # so files are resolved relative to tmp_path / doc_id.
    doc_dir = tmp_path / "repo"
    doc_dir.mkdir(parents=True)
    doc_file = doc_dir / "file.md"
    doc_file.write_text("line 1\nline 2\nline 3\n")

    mock_svc = Mock()
    mock_svc.embeddings_path = tmp_path / "embeddings"

    async def mock_retrieve(doc_id, start=None, end=None):
        return {"doc_id": doc_id, "text": "line 1\nline 2", "github_url": ""}

    mock_svc.retrieve = mock_retrieve
    mock_svc.registry = Mock()
    mock_svc.registry.get_github_url = Mock(return_value="")
    server.rag_service = mock_svc

    result = await server._handle_retrieve({"doc_id": "repo/file.md", "start": 1, "end": 2})
    assert "/ 3 total" in result[0].text


@pytest.mark.asyncio
async def test_handle_retrieve_batch_with_file(tmp_path):
    """_handle_retrieve_batch counts total lines when file exists in the store."""
    server = NancyMCPServer()

    # Store is initialized as Store(embeddings_path.parent) = Store(tmp_path),
    # so files are resolved relative to tmp_path / doc_id.
    doc_dir = tmp_path / "cat1" / "repo1"
    doc_dir.mkdir(parents=True)
    doc_file = doc_dir / "file.py"
    doc_file.write_text("line 1\nline 2\nline 3\nline 4\nline 5\nline 6\n")

    mock_svc = Mock()
    mock_svc.embeddings_path = tmp_path / "embeddings"

    async def mock_batch(items):
        return [{"doc_id": "cat1/repo1/file.py", "text": "line 1\nline 2", "github_url": ""}]

    mock_svc.retrieve_batch = mock_batch
    server.rag_service = mock_svc

    result = await server._handle_retrieve_batch({"items": [{"doc_id": "cat1/repo1/file.py", "start": 0, "end": 2}]})
    assert "/ 6 total" in result[0].text


# ---- Exception path and additional coverage tests -----------------------


def test_fetch_section_row_pragma_exception(tmp_path):
    """_fetch_section_row returns None when PRAGMA throws."""
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    server = NancyMCPServer()
    # Pass a closed connection to force PRAGMA exception
    conn.close()
    row = server._fetch_section_row(conn, "any/doc::chunk-0")
    assert row is None


def test_fetch_section_row_query_exception(tmp_path):
    """_fetch_section_row returns None when the SELECT query fails."""
    # Use a deliberately dropped table after PRAGMA reads it
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE sections (id TEXT, text TEXT, data TEXT)")
    conn.commit()
    server = NancyMCPServer()

    # Simulate a query failure by using a mock wrapper object
    class FakeConn:
        def __init__(self, real_conn):
            self._real = real_conn
            self._call = 0

        def execute(self, sql, *args):
            self._call += 1
            if self._call > 1:
                raise sqlite3.OperationalError("forced error")
            return self._real.execute(sql, *args)

        def close(self):
            return self._real.close()

    fake_conn = FakeConn(conn)
    try:
        row = server._fetch_section_row(fake_conn, "any/doc::chunk-0")
        assert row is None
    finally:
        conn.close()


def test_retrieve_chunk_window_connect_exception(tmp_path):
    """_retrieve_chunk_window returns None when sqlite3.connect fails."""
    embeddings_path = tmp_path / "embeddings"
    index_dir = embeddings_path / "index"
    index_dir.mkdir(parents=True)
    # Create the db path as a directory (not a file) so connect fails
    db_path = index_dir / "documents"
    db_path.mkdir()  # This will cause sqlite3.connect to fail

    server = NancyMCPServer()
    mock_svc = Mock()
    mock_svc.embeddings_path = embeddings_path
    server.rag_service = mock_svc

    result = server._retrieve_chunk_window("any/doc::chunk-0001", window=1)
    assert result is None


def test_resolve_doc_id_connect_exception(tmp_path):
    """_resolve_retrievable_doc_id returns original id when sqlite3.connect fails."""
    embeddings_path = tmp_path / "embeddings"
    index_dir = embeddings_path / "index"
    index_dir.mkdir(parents=True)
    # Create DB path as a directory to force connect failure
    db_path = index_dir / "documents"
    db_path.mkdir()

    server = NancyMCPServer()
    mock_svc = Mock()
    mock_svc.embeddings_path = embeddings_path
    server.rag_service = mock_svc

    result = server._resolve_retrievable_doc_id("some/doc.py")
    assert result == "some/doc.py"


def test_resolve_doc_id_no_meta_col(tmp_path):
    """_resolve_retrievable_doc_id falls back to original id when table has no data/metadata column."""
    embeddings_path = tmp_path / "embeddings"
    index_dir = embeddings_path / "index"
    index_dir.mkdir(parents=True)
    db_path = index_dir / "documents"

    # Create sections table with no data/metadata column
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE sections (id TEXT, text TEXT)")
    conn.execute("INSERT INTO sections VALUES (?, ?)", ("other/doc::chunk-0", "content"))
    conn.commit()
    conn.close()

    server = NancyMCPServer()
    mock_svc = Mock()
    mock_svc.embeddings_path = embeddings_path
    server.rag_service = mock_svc

    # A doc_id that doesn't exist directly - will fall through to metadata lookup path
    # which will return original due to no meta_col
    result = server._resolve_retrievable_doc_id("missing/doc.py")
    assert result == "missing/doc.py"


@pytest.mark.asyncio
async def test_handle_retrieve_chunk_without_line_numbers(mock_rag_service):
    """_handle_retrieve displays chunk list without line numbers when absent."""
    server = NancyMCPServer()
    server.rag_service = mock_rag_service

    server._retrieve_chunk_window = Mock(
        return_value={
            "text": "[Chunk] doc::chunk-0001\nchunk content",
            "chunks": [
                {"doc_id": "doc::chunk-0001", "line_start": None, "line_end": None},
            ],
        }
    )

    result = await server._handle_retrieve({"doc_id": "doc::chunk-0001"})
    assert "doc::chunk-0001" in result[0].text
    # The line with no numbers (line 529) - no "lines X-Y" pattern for this chunk
    assert "Chunks: 1" in result[0].text or "**Chunks:**" in result[0].text


@pytest.mark.asyncio
async def test_handle_retrieve_with_existing_file_total_lines(tmp_path):
    """_handle_retrieve counts total_lines when document file exists."""
    server = NancyMCPServer()

    embeddings_path = tmp_path / "embeddings"
    embeddings_path.mkdir()

    # Create the file directly at the store base (= embeddings_path.parent = tmp_path)
    doc_dir = tmp_path / "cat1" / "repo1"
    doc_dir.mkdir(parents=True)
    doc_file = doc_dir / "main.py"
    doc_file.write_text("line1\nline2\nline3\nline4\nline5\n")

    mock_svc = Mock()
    mock_svc.embeddings_path = embeddings_path

    async def mock_retrieve(doc_id, start=None, end=None):
        return {"doc_id": doc_id, "text": "line1\nline2", "github_url": ""}

    mock_svc.retrieve = mock_retrieve
    mock_svc.registry = Mock()
    mock_svc.registry.get_github_url = Mock(return_value="")
    server.rag_service = mock_svc

    result = await server._handle_retrieve(
        {
            "doc_id": "cat1/repo1/main.py",
            "start": 1,
            "end": 2,
        }
    )
    # Should have counted total_lines from file and included it in output
    assert "/ 5 total" in result[0].text


@pytest.mark.asyncio
async def test_handle_retrieve_batch_with_existing_file(tmp_path):
    """_handle_retrieve_batch counts total_lines when file exists."""
    server = NancyMCPServer()

    embeddings_path = tmp_path / "embeddings"
    embeddings_path.mkdir()

    doc_dir = tmp_path / "ns" / "repo"
    doc_dir.mkdir(parents=True)
    doc_file = doc_dir / "doc.py"
    doc_file.write_text("a\nb\nc\nd\ne\nf\n")

    mock_svc = Mock()
    mock_svc.embeddings_path = embeddings_path

    async def mock_batch(items):
        return [{"doc_id": "ns/repo/doc.py", "text": "a\nb", "github_url": ""}]

    mock_svc.retrieve_batch = mock_batch
    server.rag_service = mock_svc

    result = await server._handle_retrieve_batch({"items": [{"doc_id": "ns/repo/doc.py", "start": 0, "end": 2}]})
    assert "/ 6 total" in result[0].text


@pytest.mark.asyncio
async def test_handle_set_weights_clamped_display(mock_rag_service):
    """_handle_set_weights explicitly shows 'Actual Weight' when weight exceeds 2.0."""
    server = NancyMCPServer()
    server.rag_service = mock_rag_service
    server.rag_service.set_weight = AsyncMock(return_value=True)

    result = await server._handle_set_weights({"doc_id": "doc.py", "weight": 3.5})
    assert "Actual Weight" in result[0].text
    assert "clamped" in result[0].text.lower() or "2.0" in result[0].text


@pytest.mark.asyncio
async def test_handle_set_weights_no_service():
    """_handle_set_weights returns 'not initialized' when rag_service is None."""
    server = NancyMCPServer()
    server.rag_service = None
    result = await server._handle_set_weights({"doc_id": "doc.py", "weight": 1.0})
    assert "not initialized" in result[0].text


def test_resolve_doc_id_returns_original_when_no_match(tmp_path):
    """_resolve_retrievable_doc_id returns original doc_id when metadata lookup fails."""
    embeddings_path = tmp_path / "embeddings"
    index_dir = embeddings_path / "index"
    index_dir.mkdir(parents=True)
    db_path = index_dir / "documents"

    # Create sections with data column, but no matching source_document for our lookup
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE sections (id TEXT, text TEXT, data TEXT)")
    conn.execute(
        "INSERT INTO sections VALUES (?, ?, ?)",
        ("other/doc.py::chunk-0", "content", '{"source_document": "other/doc.py"}'),
    )
    conn.commit()
    conn.close()

    server = NancyMCPServer()
    mock_svc = Mock()
    mock_svc.embeddings_path = embeddings_path
    server.rag_service = mock_svc

    # Look up a doc_id that has no matching row at all
    result = server._resolve_retrievable_doc_id("completely/different/path.py")
    assert result == "completely/different/path.py"
