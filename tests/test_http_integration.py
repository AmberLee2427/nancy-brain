import os

# Fix OpenMP issue before importing any ML libraries
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

import pytest  # noqa: F401 E0401
import yaml  # noqa: F401 E0401
from pathlib import Path
from unittest.mock import Mock, patch, AsyncMock
from fastapi.testclient import TestClient


@pytest.fixture()
def mock_rag_service():
    """Provide a mock RAG service with all required async methods."""
    mock = Mock()

    async def mock_health():
        return {"status": "ok"}

    async def mock_version():
        return {
            "index_version": "test",
            "build_sha": "test123",
            "built_at": "2024-01-01T00:00:00Z",
        }

    async def mock_search_docs(query, limit=10, **kwargs):
        return [{"id": "cat1/repoA/test", "text": "test content", "score": 0.9}]

    async def mock_retrieve(doc_id, start, end):
        return {
            "doc_id": doc_id,
            "text": "line 1\nline 2",
            "github_url": f"https://example.com/{doc_id}",
            "content_sha256": "deadbeef",
            "index_version": "test",
        }

    async def mock_retrieve_batch(items):
        passages = []
        for it in items:
            passages.append(
                {
                    "doc_id": it["doc_id"],
                    "text": "line 1\nline 2",
                    "github_url": f"https://example.com/{it['doc_id']}",
                    "content_sha256": "deadbeef",
                    "index_version": "test",
                }
            )
        return passages

    async def mock_list_tree(**kwargs):
        return [{"path": "cat1/repoA/test", "type": "file"}]

    mock.health = mock_health
    mock.version = mock_version
    mock.search_docs = mock_search_docs
    mock.retrieve = mock_retrieve
    mock.retrieve_batch = mock_retrieve_batch
    mock.list_tree = mock_list_tree
    mock.set_weight = AsyncMock()
    return mock


@pytest.fixture()
def client_with_rag(tmp_path, mock_rag_service):
    """Yield a TestClient with dependency override and test KB layout."""
    # Prepare minimal repo layout
    config = {"cat1": [{"name": "repoA", "url": "https://github.com/user/repoA.git"}]}
    (tmp_path / "repositories.yml").write_text(yaml.safe_dump(config))
    (tmp_path / "embeddings").mkdir()
    raw_path = tmp_path / "raw" / "cat1" / "repoA"
    raw_path.mkdir(parents=True)
    (raw_path / "test").write_text("line 1\nline 2\nline 3\n")
    (tmp_path / "weights.yaml").write_text("extensions: {}")

    import connectors.http_api.app as mod
    from connectors.http_api.app import app, get_rag_service, verify_auth

    original = getattr(mod, "rag_service", None)
    mod.rag_service = mock_rag_service  # keep global for legacy access

    def _get():
        return mock_rag_service

    app.dependency_overrides[get_rag_service] = _get

    client = TestClient(app)
    try:
        # Override dependency injection for testing
        def mock_verify_auth():
            return "mock_token"

        app.dependency_overrides[verify_auth] = mock_verify_auth
        yield client
    finally:
        app.dependency_overrides.clear()
        mod.rag_service = original


def test_http_with_rag_service(client_with_rag):
    """Test core HTTP endpoints with mocked RAG service."""
    headers = {"Authorization": "Bearer test-token"}

    # Health
    r = client_with_rag.get("/health", headers=headers)
    assert r.status_code == 200
    data = r.json()
    assert data["status"] in ["ok", "degraded"]

    # Version
    r = client_with_rag.get("/version", headers=headers)
    assert r.status_code == 200
    assert "index_version" in r.json()

    # Search
    r = client_with_rag.get("/search?query=test&limit=5", headers=headers)
    assert r.status_code == 200
    data = r.json()
    assert len(data["hits"]) == 1

    # Retrieve
    r = client_with_rag.post(
        "/retrieve",
        headers=headers,
        json={"doc_id": "cat1/repoA/test", "start": 0, "end": 2},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["passage"]["doc_id"] == "cat1/repoA/test"

    # Tree
    r = client_with_rag.get("/tree?prefix=cat1", headers=headers)
    assert r.status_code == 200
    assert len(r.json()["entries"]) > 0


def test_http_retrieve_batch(client_with_rag):
    """Test batch retrieval endpoint."""
    headers = {"Authorization": "Bearer test-token"}
    payload = {
        "items": [
            {"doc_id": "cat1/repoA/test", "start": 0, "end": 1},
            {"doc_id": "cat1/repoA/test", "start": 1, "end": 2},
        ]
    }
    r = client_with_rag.post("/retrieve/batch", headers=headers, json=payload)
    assert r.status_code == 200
    data = r.json()
    assert len(data["passages"]) == 2
    for p in data["passages"]:
        assert p["doc_id"] == "cat1/repoA/test"


def test_http_set_weight_calls_service(client_with_rag, mock_rag_service):
    headers = {"Authorization": "Bearer test-token"}
    payload = {"doc_id": "cat1/repoA/test", "multiplier": 2.0}
    r = client_with_rag.post("/weight", headers=headers, json=payload)
    assert r.status_code == 200
    mock_rag_service.set_weight.assert_awaited_once()


def test_http_error_responses():
    import connectors.http_api.app as mod
    from connectors.http_api.app import app, reset_rag_service

    original = getattr(mod, "rag_service", None)
    try:
        reset_rag_service()
        client = TestClient(app)
        headers = {"Authorization": "Bearer test-token"}
        r = client.get("/health", headers=headers)
        assert r.status_code == 503
        data = r.json()
        assert "RAG service not initialized" in data["detail"]

        r = client.post("/retrieve", headers=headers, json={"invalid": "data"})
        assert r.status_code in [422, 503]
    finally:
        mod.rag_service = original
