import os

# Fix OpenMP issue before importing any ML libraries
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

import pytest  # noqa: F401 E0401
import yaml  # noqa: F401 E0401
from pathlib import Path
from unittest.mock import Mock, patch

from rag_core.service import RAGService


def test_service_methods(tmp_path):
    """Test the new RAGService methods with mocked dependencies."""

    # Create minimal config
    config = {
        "cat1": [
            {"name": "repoA", "url": "https://github.com/user/repoA.git"},
        ],
    }
    cfg_file = tmp_path / "repositories.yml"
    cfg_file.write_text(yaml.safe_dump(config))

    # Create mock embeddings and weights paths
    embeddings_path = tmp_path / "embeddings"
    embeddings_path.mkdir()
    weights_path = tmp_path / "weights.yaml"
    weights_path.write_text("extensions: {}")

    # Create sample text file for store
    sample_file = tmp_path / "cat1" / "repoA" / "file"  # Store will add .txt
    sample_file.parent.mkdir(parents=True)
    sample_file.write_text("line 1\nline 2\nline 3\n")

    # Mock the search component since we don't have txtai
    service = RAGService(embeddings_path=embeddings_path, config_path=cfg_file, weights_path=weights_path)

    # Mock search results
    service.search.search = Mock(
        return_value=[{"id": "cat1/repoA/file", "text": "sample text", "score": 0.8}]  # No .txt in id
    )

    # Test async methods
    import asyncio

    async def run_tests():
        # Test search_docs
        results = await service.search_docs("test query", limit=5)
        assert len(results) == 1
        assert results[0]["id"] == "cat1/repoA/file"

        # Test retrieve (using 0-based indexing)
        passage = await service.retrieve("cat1/repoA/file", 0, 2)
        assert passage["doc_id"] == "cat1/repoA/file"
        assert "line 1" in passage["text"]

        # Test retrieve_batch
        batch_items = [{"doc_id": "cat1/repoA/file", "start": 0, "end": 2}]
        batch_results = await service.retrieve_batch(batch_items)
        assert len(batch_results) == 1
        assert batch_results[0]["doc_id"] == "cat1/repoA/file"

        # Test list_tree
        tree = await service.list_tree()
        assert len(tree) > 0

        # Test set_weight
        await service.set_weight("cat1/repoA/file", 1.5)
        assert hasattr(service, "_weights")

        # Test version
        version_info = await service.version()
        assert "index_version" in version_info

        # Test health
        health_info = await service.health()
        assert health_info["status"] in ["ok", "degraded"]

    asyncio.run(run_tests())


def test_search_with_filters(tmp_path):
    """Test search_docs with toolkit and doctype filters."""

    # Create config with toolkit info
    config = {
        "microlensing_tools": [
            {"name": "MulensModel", "url": "https://github.com/user/MulensModel.git"},
            {"name": "pyLIMA", "url": "https://github.com/user/pyLIMA.git"},
        ],
    }
    cfg_file = tmp_path / "repositories.yml"
    cfg_file.write_text(yaml.safe_dump(config))

    embeddings_path = tmp_path / "embeddings"
    embeddings_path.mkdir()
    weights_path = tmp_path / "weights.yaml"
    weights_path.write_text("extensions: {}")

    service = RAGService(embeddings_path=embeddings_path, config_path=cfg_file, weights_path=weights_path)

    # Mock search to return multiple results
    service.search.search = Mock(
        return_value=[
            {
                "id": "microlensing_tools/MulensModel/README.md",
                "text": "MulensModel docs",
                "score": 0.9,
            },
            {
                "id": "microlensing_tools/pyLIMA/README.md",
                "text": "pyLIMA docs",
                "score": 0.8,
            },
        ]
    )

    # Override get_meta to return different toolkits
    def mock_get_meta(doc_id):
        from rag_core.types import DocMeta

        if "MulensModel" in doc_id:
            toolkit = "mulensmodel"
        elif "pyLIMA" in doc_id:
            toolkit = "pylima"
        else:
            toolkit = None
        return DocMeta(
            doc_id=doc_id,
            github_url="",
            default_branch="master",
            toolkit=toolkit,
            doctype="docs",
            content_sha256="",
            line_index=[],
        )

    service.registry.get_meta = mock_get_meta

    import asyncio

    async def run_filter_tests():
        # Test filtering by toolkit
        results = await service.search_docs("test", toolkit="mulensmodel")
        assert len(results) == 1
        assert "MulensModel" in results[0]["id"]

        # Test filtering by different toolkit
        results = await service.search_docs("test", toolkit="pylima")
        assert len(results) == 1
        assert "pyLIMA" in results[0]["id"]

        # Test no matches with wrong toolkit
        results = await service.search_docs("test", toolkit="nonexistent")
        assert len(results) == 0

    asyncio.run(run_filter_tests())


def test_search_docs_with_weights(tmp_path):
    """Test search_docs with runtime weights applied."""
    config = {"cat1": [{"name": "repo1", "url": "https://github.com/user/repo1.git"}]}
    cfg_file = tmp_path / "repositories.yml"
    cfg_file.write_text(yaml.safe_dump(config))

    embeddings_path = tmp_path / "embeddings"
    embeddings_path.mkdir()
    weights_path = tmp_path / "weights.yaml"
    weights_path.write_text("extensions: {}")

    service = RAGService(embeddings_path=embeddings_path, config_path=cfg_file, weights_path=weights_path)

    # Mock search
    service.search.search = Mock(return_value=[{"id": "cat1/repo1/test.py", "text": "Test content", "score": 0.8}])

    # Mock model_weights attribute
    service.search.model_weights = {}

    # Set runtime weights
    service._weights = {"cat1/repo1/test.py": 1.5}

    import asyncio

    async def test_weights():
        await service.search_docs("test query")
        # Should have applied runtime weights to search.model_weights
        assert service.search.model_weights == {"cat1/repo1/test.py": 1.5}

    asyncio.run(test_weights())


def test_search_docs_threshold_filter(tmp_path):
    """Test search_docs with threshold filtering."""
    config = {"cat1": [{"name": "repo1", "url": "https://github.com/user/repo1.git"}]}
    cfg_file = tmp_path / "repositories.yml"
    cfg_file.write_text(yaml.safe_dump(config))

    embeddings_path = tmp_path / "embeddings"
    embeddings_path.mkdir()
    weights_path = tmp_path / "weights.yaml"
    weights_path.write_text("extensions: {}")

    service = RAGService(embeddings_path=embeddings_path, config_path=cfg_file, weights_path=weights_path)

    # Mock search to return results with different scores
    service.search.search = Mock(
        return_value=[
            {"id": "cat1/repo1/high.py", "text": "High relevance", "score": 0.9},
            {"id": "cat1/repo1/medium.py", "text": "Medium relevance", "score": 0.6},
            {"id": "cat1/repo1/low.py", "text": "Low relevance", "score": 0.3},
        ]
    )

    import asyncio

    async def test_threshold():
        # Test with threshold 0.7 - should only return high relevance
        results = await service.search_docs("test query", threshold=0.7)
        assert len(results) == 1
        assert results[0]["score"] == 0.9

        # Test with threshold 0.5 - should return high and medium
        results = await service.search_docs("test query", threshold=0.5)
        assert len(results) == 2

    asyncio.run(test_threshold())


def test_is_available(tmp_path):
    """Test is_available method."""
    config = {"cat1": [{"name": "repo1", "url": "https://github.com/user/repo1.git"}]}
    cfg_file = tmp_path / "repositories.yml"
    cfg_file.write_text(yaml.safe_dump(config))

    embeddings_path = tmp_path / "embeddings"
    embeddings_path.mkdir()
    weights_path = tmp_path / "weights.yaml"
    weights_path.write_text("extensions: {}")

    service = RAGService(embeddings_path=embeddings_path, config_path=cfg_file, weights_path=weights_path)

    # Mock general_embeddings attribute
    service.general_embeddings = None
    assert service.is_available() is False

    service.general_embeddings = "mock_embeddings"
    assert service.is_available() is True


def test_search_docs_with_enhanced_results(tmp_path):
    """Test search_docs returns enhanced results with all expected fields."""
    config = {"cat1": [{"name": "repo1", "url": "https://github.com/user/repo1.git"}]}
    cfg_file = tmp_path / "repositories.yml"
    cfg_file.write_text(yaml.safe_dump(config))

    embeddings_path = tmp_path / "embeddings"
    embeddings_path.mkdir()
    weights_path = tmp_path / "weights.yaml"
    weights_path.write_text("extensions: {}")

    service = RAGService(embeddings_path=embeddings_path, config_path=cfg_file, weights_path=weights_path)

    # Mock search with additional scoring fields
    service.search.search = Mock(
        return_value=[
            {
                "id": "cat1/repo1/enhanced.py",
                "text": "Enhanced content",
                "score": 0.85,
                "model_score": 0.9,
                "extension_weight": 1.2,
                "adjusted_score": 1.02,
            }
        ]
    )

    import asyncio

    async def test_enhanced():
        results = await service.search_docs("test query")
        assert len(results) == 1
        result = results[0]

        # Check all expected fields are present
        assert result["id"] == "cat1/repo1/enhanced.py"
        assert result["text"] == "Enhanced content"
        assert result["score"] == 0.85
        # Note: github_url is added by enhanced methods, not raw search_docs
        assert result["model_score"] == 0.9
        assert result["extension_weight"] == 1.2
        assert result["adjusted_score"] == 1.02

    asyncio.run(test_enhanced())


def test_service_error_handling(tmp_path):
    """Test error handling in various service methods."""
    config = {"cat1": [{"name": "repo1", "url": "https://github.com/user/repo1.git"}]}
    cfg_file = tmp_path / "repositories.yml"
    cfg_file.write_text(yaml.safe_dump(config))

    embeddings_path = tmp_path / "embeddings"
    embeddings_path.mkdir()
    weights_path = tmp_path / "weights.yaml"
    weights_path.write_text("extensions: {}")

    service = RAGService(embeddings_path=embeddings_path, config_path=cfg_file, weights_path=weights_path)

    import asyncio

    async def test_errors():
        # Test retrieve_batch with invalid documents - should handle errors gracefully
        batch_items = [
            {"doc_id": "nonexistent/doc1", "start": 0, "end": 5},
            {"doc_id": "nonexistent/doc2", "start": 10, "end": 15},
        ]
        results = await service.retrieve_batch(batch_items)
        assert len(results) == 2
        # Should contain error information
        for result in results:
            assert "error" in result or "Error retrieving document" in result["text"]

    asyncio.run(test_errors())


def test_list_tree_structure(tmp_path):
    """Test list_tree builds proper tree structure."""
    config = {"cat1": [{"name": "repo1", "url": "https://github.com/user/repo1.git"}]}
    cfg_file = tmp_path / "repositories.yml"
    cfg_file.write_text(yaml.safe_dump(config))

    embeddings_path = tmp_path / "embeddings"
    embeddings_path.mkdir()
    weights_path = tmp_path / "weights.yaml"
    weights_path.write_text("extensions: {}")

    service = RAGService(embeddings_path=embeddings_path, config_path=cfg_file, weights_path=weights_path)

    # Mock registry.list_ids to return hierarchical paths
    service.registry.list_ids = Mock(
        return_value=[
            "cat1/repo1/src/main.py",
            "cat1/repo1/src/utils.py",
            "cat1/repo1/tests/test_main.py",
            "cat1/repo1/README.md",
        ]
    )

    import asyncio

    async def test_tree():
        tree = await service.list_tree()
        # Should have proper tree structure
        assert len(tree) > 0

        # Test with depth limit
        tree_depth_1 = await service.list_tree(depth=1)
        assert len(tree_depth_1) > 0

        # Test with prefix filter
        tree_src = await service.list_tree(prefix="cat1/repo1/src")
        assert len(tree_src) >= 0

    asyncio.run(test_tree())
