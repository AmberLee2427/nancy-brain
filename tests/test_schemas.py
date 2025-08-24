"""
Tests for HTTP API schemas.
"""

import pytest
from pydantic import ValidationError

from connectors.http_api.schemas import (
    SearchHitSchema,
    SearchResponseSchema,
    PassageSchema,
    RetrieveRequestSchema,
    RetrieveBatchRequestSchema,
    RetrieveResponseSchema,
    RetrieveBatchResponseSchema,
    TreeEntrySchema,
    TreeResponseSchema,
    SetWeightRequestSchema,
    VersionResponseSchema,
    HealthResponseSchema,
    ErrorResponseSchema,
    SEARCH_EXAMPLE,
    RETRIEVE_EXAMPLE,
)


def test_search_hit_schema():
    """Test SearchHitSchema validation."""
    data = {"id": "test/doc", "text": "test content", "score": 0.95}
    hit = SearchHitSchema(**data)
    assert hit.id == "test/doc"
    assert hit.text == "test content"
    assert hit.score == 0.95


def test_search_response_schema():
    """Test SearchResponseSchema validation."""
    data = {
        "hits": [{"id": "test/doc", "text": "test content", "score": 0.95}],
        "index_version": "v1.0",
        "trace_id": "trace-123",
    }
    response = SearchResponseSchema(**data)
    assert len(response.hits) == 1
    assert response.hits[0].id == "test/doc"
    assert response.index_version == "v1.0"
    assert response.trace_id == "trace-123"


def test_passage_schema():
    """Test PassageSchema validation."""
    data = {
        "doc_id": "test/doc",
        "text": "passage content",
        "github_url": "https://github.com/test/repo",
        "content_sha256": "abc123",
        "index_version": "v1.0",
    }
    passage = PassageSchema(**data)
    assert passage.doc_id == "test/doc"
    assert passage.text == "passage content"
    assert passage.github_url == "https://github.com/test/repo"
    assert passage.content_sha256 == "abc123"
    assert passage.index_version == "v1.0"


def test_passage_schema_defaults():
    """Test PassageSchema with default values."""
    data = {
        "doc_id": "test/doc",
        "text": "passage content",
        "github_url": "https://github.com/test/repo",
        "content_sha256": "abc123",
    }
    passage = PassageSchema(**data)
    assert passage.index_version == ""  # Default value


def test_retrieve_request_schema():
    """Test RetrieveRequestSchema validation."""
    data = {"doc_id": "test/doc", "start": 1, "end": 10}
    request = RetrieveRequestSchema(**data)
    assert request.doc_id == "test/doc"
    assert request.start == 1
    assert request.end == 10


def test_retrieve_batch_request_schema():
    """Test RetrieveBatchRequestSchema validation."""
    data = {
        "items": [
            {"doc_id": "test/doc1", "start": 1, "end": 10},
            {"doc_id": "test/doc2", "start": 5, "end": 15},
        ]
    }
    request = RetrieveBatchRequestSchema(**data)
    assert len(request.items) == 2
    assert request.items[0].doc_id == "test/doc1"
    assert request.items[1].doc_id == "test/doc2"


def test_retrieve_response_schema():
    """Test RetrieveResponseSchema validation."""
    data = {
        "passage": {
            "doc_id": "test/doc",
            "text": "passage content",
            "github_url": "https://github.com/test/repo",
            "content_sha256": "abc123",
        },
        "trace_id": "trace-123",
    }
    response = RetrieveResponseSchema(**data)
    assert response.passage.doc_id == "test/doc"
    assert response.trace_id == "trace-123"


def test_retrieve_batch_response_schema():
    """Test RetrieveBatchResponseSchema validation."""
    data = {
        "passages": [
            {
                "doc_id": "test/doc1",
                "text": "content1",
                "github_url": "https://github.com/test/repo",
                "content_sha256": "abc123",
            },
            {
                "doc_id": "test/doc2",
                "text": "content2",
                "github_url": "https://github.com/test/repo",
                "content_sha256": "def456",
            },
        ],
        "trace_id": "trace-123",
    }
    response = RetrieveBatchResponseSchema(**data)
    assert len(response.passages) == 2
    assert response.passages[0].doc_id == "test/doc1"
    assert response.passages[1].doc_id == "test/doc2"


def test_tree_entry_schema():
    """Test TreeEntrySchema validation."""
    data = {"path": "src/main.py", "type": "file", "size": 1024}
    entry = TreeEntrySchema(**data)
    assert entry.path == "src/main.py"
    assert entry.type == "file"
    assert entry.size == 1024


def test_tree_entry_schema_no_size():
    """Test TreeEntrySchema without size."""
    data = {"path": "src/", "type": "directory"}
    entry = TreeEntrySchema(**data)
    assert entry.path == "src/"
    assert entry.type == "directory"
    assert entry.size is None


def test_tree_response_schema():
    """Test TreeResponseSchema validation."""
    data = {
        "entries": [
            {"path": "src/main.py", "type": "file", "size": 1024},
            {"path": "docs/", "type": "directory"},
        ],
        "trace_id": "trace-123",
    }
    response = TreeResponseSchema(**data)
    assert len(response.entries) == 2
    assert response.entries[0].path == "src/main.py"
    assert response.entries[1].type == "directory"


def test_set_weight_request_schema():
    """Test SetWeightRequestSchema validation."""
    data = {"doc_id": "test/doc", "multiplier": 1.5, "namespace": "test", "ttl_days": 7}
    request = SetWeightRequestSchema(**data)
    assert request.doc_id == "test/doc"
    assert request.multiplier == 1.5
    assert request.namespace == "test"
    assert request.ttl_days == 7


def test_set_weight_request_defaults():
    """Test SetWeightRequestSchema with defaults."""
    data = {"doc_id": "test/doc", "multiplier": 1.5}
    request = SetWeightRequestSchema(**data)
    assert request.namespace == "global"
    assert request.ttl_days is None


def test_version_response_schema():
    """Test VersionResponseSchema validation."""
    data = {
        "index_version": "v1.0",
        "build_sha": "abc123",
        "built_at": "2025-08-24T12:00:00Z",
        "trace_id": "trace-123",
    }
    response = VersionResponseSchema(**data)
    assert response.index_version == "v1.0"
    assert response.build_sha == "abc123"
    assert response.built_at == "2025-08-24T12:00:00Z"


def test_health_response_schema():
    """Test HealthResponseSchema validation."""
    data = {"status": "healthy", "trace_id": "trace-123"}
    response = HealthResponseSchema(**data)
    assert response.status == "healthy"
    assert response.trace_id == "trace-123"


def test_error_response_schema():
    """Test ErrorResponseSchema validation."""
    data = {
        "error": "Something went wrong",
        "trace_id": "trace-123",
        "detail": "More info",
    }
    response = ErrorResponseSchema(**data)
    assert response.error == "Something went wrong"
    assert response.trace_id == "trace-123"
    assert response.detail == "More info"


def test_error_response_schema_no_detail():
    """Test ErrorResponseSchema without detail."""
    data = {"error": "Something went wrong", "trace_id": "trace-123"}
    response = ErrorResponseSchema(**data)
    assert response.error == "Something went wrong"
    assert response.detail is None


def test_search_example():
    """Test that SEARCH_EXAMPLE is valid."""
    assert "summary" in SEARCH_EXAMPLE
    assert "value" in SEARCH_EXAMPLE
    assert "query" in SEARCH_EXAMPLE["value"]
    assert SEARCH_EXAMPLE["value"]["query"] == "MulensModel PSPL parameters"


def test_retrieve_example():
    """Test that RETRIEVE_EXAMPLE is valid."""
    assert "summary" in RETRIEVE_EXAMPLE
    assert "value" in RETRIEVE_EXAMPLE
    assert "doc_id" in RETRIEVE_EXAMPLE["value"]
    assert RETRIEVE_EXAMPLE["value"]["doc_id"] == "microlensing_tools/MulensModel/README.md"


def test_invalid_search_hit_schema():
    """Test SearchHitSchema validation with invalid data."""
    with pytest.raises(ValidationError):
        SearchHitSchema(id="test", text="content")  # Missing score


def test_invalid_retrieve_request():
    """Test RetrieveRequestSchema validation with invalid data."""
    with pytest.raises(ValidationError):
        RetrieveRequestSchema(doc_id="test")  # Missing start and end
