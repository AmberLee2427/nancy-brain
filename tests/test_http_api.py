import pytest  # noqa: F401 E0401
import yaml  # noqa: F401 E0401
from pathlib import Path
from unittest.mock import Mock, patch
from fastapi.testclient import TestClient

from connectors.http_api.app import app, initialize_rag_service, get_rag_service


@pytest.fixture(autouse=True)
def reset_app_state():
    """Reset the app's global state before and after each test."""
    # Store original state
    import connectors.http_api.app as app_module

    original_rag_service = getattr(app_module, "rag_service", None)
    original_overrides = app.dependency_overrides.copy()

    yield  # Run the test

    # Restore original state
    app_module.rag_service = original_rag_service
    app.dependency_overrides.clear()
    app.dependency_overrides.update(original_overrides)


def test_http_app_startup(tmp_path):
    """Test that the FastAPI app can start up with mocked RAG service."""

    # Create a mock RAG service instance
    mock_rag = Mock()

    # Mock the async methods
    async def mock_health():
        return {"status": "ok"}

    async def mock_version():
        return {
            "index_version": "test-1.0",
            "build_sha": "abc123",
            "built_at": "2025-08-23T12:00:00Z",
        }

    async def mock_search_docs(query, limit=6, toolkit=None, doctype=None, threshold=0.0):
        return [{"id": "cat1/repoA/test.md", "text": "test content", "score": 0.9}]

    mock_rag.health = mock_health
    mock_rag.version = mock_version
    mock_rag.search_docs = mock_search_docs

    # Mock the dependency
    def mock_get_rag_service():
        return mock_rag

    # Use dependency override
    app.dependency_overrides[get_rag_service] = mock_get_rag_service

    try:
        # Create test client
        client = TestClient(app)
        headers = {"Authorization": "Bearer test-token"}

        # Test health endpoint
        response = client.get("/health", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "trace_id" in data

        # Test version endpoint
        response = client.get("/version", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert data["index_version"] == "test-1.0"
        assert data["build_sha"] == "abc123"
        assert "trace_id" in data

        # Test search endpoint
        response = client.get("/search?query=test", headers=headers)
        assert response.status_code == 200
        data = response.json()
        assert len(data["hits"]) == 1
        assert data["hits"][0]["id"] == "cat1/repoA/test.md"
        assert data["index_version"] == "test-1.0"
        assert "trace_id" in data
    finally:
        # Clean up dependency override
        app.dependency_overrides.clear()


def test_http_auth_required():
    """Test that endpoints require authentication."""

    # Create a mock RAG service for dependency injection
    mock_rag = Mock()

    async def mock_health():
        return {"status": "ok"}

    mock_rag.health = mock_health

    def mock_get_rag_service():
        return mock_rag

    # Use dependency override
    app.dependency_overrides[get_rag_service] = mock_get_rag_service

    try:
        client = TestClient(app)

        # Test without authorization header - should get 403 because security dependency fails first
        response = client.get("/health")
        assert response.status_code == 403  # Forbidden due to missing auth

        response = client.get("/version")
        assert response.status_code == 403

        response = client.get("/search?query=test")
        assert response.status_code == 403
    finally:
        # Clean up dependency override
        app.dependency_overrides.clear()


def test_http_retrieve_endpoint(tmp_path):
    """Test the retrieve endpoint with mocked data."""

    mock_rag = Mock()

    # Mock retrieve method
    async def mock_retrieve(doc_id, start=None, end=None):
        return {
            "doc_id": doc_id,
            "text": "line 1\nline 2\nline 3\n",
            "github_url": "https://github.com/user/repoA/blob/master/test.md",
            "content_sha256": "abcdef123456",
        }

    async def mock_retrieve_batch(items):
        results = []
        for item in items:
            result = await mock_retrieve(item["doc_id"], item.get("start"), item.get("end"))
            results.append(result)
        return results

    mock_rag.retrieve = mock_retrieve
    mock_rag.retrieve_batch = mock_retrieve_batch

    # Mock health method for completeness
    async def mock_health():
        return {"status": "ok"}

    mock_rag.health = mock_health

    # Mock the dependency
    def mock_get_rag_service():
        return mock_rag

    # Use dependency override
    app.dependency_overrides[get_rag_service] = mock_get_rag_service

    try:
        client = TestClient(app)
        headers = {"Authorization": "Bearer test-token"}

        # Test single retrieve
        response = client.post(
            "/retrieve",
            json={"doc_id": "cat1/repoA/test.md", "start": 0, "end": 2},
            headers=headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert data["passage"]["doc_id"] == "cat1/repoA/test.md"
        assert "line 1" in data["passage"]["text"]
        assert "trace_id" in data

        # Test batch retrieve
        response = client.post(
            "/retrieve/batch",
            json={
                "items": [
                    {"doc_id": "cat1/repoA/test1.md", "start": 0, "end": 2},
                    {"doc_id": "cat1/repoA/test2.md", "start": 1, "end": 3},
                ]
            },
            headers=headers,
        )
        assert response.status_code == 200
        data = response.json()
        assert len(data["passages"]) == 2
        assert data["passages"][0]["doc_id"] == "cat1/repoA/test1.md"
        assert "trace_id" in data
    finally:
        # Clean up dependency override
        app.dependency_overrides.clear()


def test_http_error_handling():
    """Test error handling when RAG service raises an exception."""

    with patch("rag_core.service.RAGService") as mock_service_class:
        mock_service = Mock()

        # Make health() raise an exception
        async def failing_health():
            raise Exception("Service is down")

        mock_service.health = failing_health
        mock_service_class.return_value = mock_service

        # Override the dependency to return our failing mock
        from connectors.http_api.app import get_rag_service

        app.dependency_overrides[get_rag_service] = lambda: mock_service

        client = TestClient(app)
        headers = {"Authorization": "Bearer test-token"}

        response = client.get("/health", headers=headers)
        assert response.status_code == 503  # Service unavailable
        assert "Health check failed: Service is down" in response.json()["detail"]
