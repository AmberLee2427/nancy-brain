import os

# Fix OpenMP issue before importing any ML libraries
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

import pytest  # noqa: F401 E0401
from fastapi.testclient import TestClient


# Simple test without auth - just test the app structure
def test_app_creation():
    """Test that the FastAPI app can be created and has the expected routes."""
    from connectors.http_api.app import app, reset_rag_service
    import connectors.http_api.app as app_module

    # Store original and ensure clean state
    original_rag_service = getattr(app_module, "rag_service", None)

    try:
        reset_rag_service()
        client = TestClient(app)
        headers = {"Authorization": "Bearer test-token"}

        # Test that the app responds (even if with auth errors)
        response = client.get("/health", headers=headers)
        # Should get 503 (service unavailable) since RAG service not initialized
        assert response.status_code == 503

        response = client.get("/version", headers=headers)
        assert response.status_code == 503

        response = client.get("/search?query=test", headers=headers)
        assert response.status_code == 503
    finally:
        app_module.rag_service = original_rag_service


def test_app_openapi_schema():
    """Test that the app generates a valid OpenAPI schema."""
    from connectors.http_api.app import app

    client = TestClient(app)

    # Get OpenAPI schema
    response = client.get("/openapi.json")
    assert response.status_code == 200

    schema = response.json()
    assert "openapi" in schema
    # FastAPI defaults to 3.1.0 now
    assert schema["openapi"] in ["3.0.3", "3.1.0"]
    assert "info" in schema
    assert schema["info"]["title"] == "Nancy RAG API"

    # Check that our endpoints are in the schema
    paths = schema["paths"]
    assert "/search" in paths
    assert "/retrieve" in paths
    assert "/retrieve/batch" in paths
    assert "/tree" in paths
    assert "/weight" in paths
    assert "/version" in paths
    assert "/health" in paths

    # Check operation IDs are present
    assert paths["/search"]["get"]["operationId"] == "search_documents"
    assert paths["/retrieve"]["post"]["operationId"] == "retrieve_passage"
    assert paths["/retrieve/batch"]["post"]["operationId"] == "retrieve_batch"


def test_app_without_rag_service():
    """Test app behavior when RAG service is not initialized."""
    from connectors.http_api.app import app, reset_rag_service
    import connectors.http_api.app as app_module

    # Store original and ensure clean state
    original_rag_service = getattr(app_module, "rag_service", None)

    try:
        reset_rag_service()
        client = TestClient(app)

        # Create a dummy token for auth
        headers = {"Authorization": "Bearer test-token"}

        # Should get service unavailable when RAG service not initialized
        response = client.get("/health", headers=headers)
        assert response.status_code == 503
        assert "RAG service not initialized" in response.json()["detail"]
    finally:
        app_module.rag_service = original_rag_service
