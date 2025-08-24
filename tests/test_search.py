import os

# Fix OpenMP issue before importing any ML libraries
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

import pytest
from pathlib import Path
from unittest.mock import Mock, patch
from rag_core.search import Search


def test_search_initialization(tmp_path):
    """Test Search class initialization."""
    embeddings_path = tmp_path / "embeddings"
    embeddings_path.mkdir()

    # Test basic initialization
    search = Search(
        embeddings_path=embeddings_path,
        dual=False,
        code_model="test-model",
        extension_weights={"py": 1.2},
        model_weights={"test": 1.0},
    )

    assert search.embeddings_path == embeddings_path
    assert search.use_dual_embedding is False
    assert search.code_model == "test-model"
    assert search.extension_weights == {"py": 1.2}
    assert search.model_weights == {"test": 1.0}


def test_search_with_dual_embedding(tmp_path):
    """Test Search initialization with dual embedding enabled."""
    embeddings_path = tmp_path / "embeddings"
    embeddings_path.mkdir()

    search = Search(embeddings_path=embeddings_path, dual=True, extension_weights={}, model_weights={})

    assert search.use_dual_embedding is True
    assert search.extension_weights == {}
    assert search.model_weights == {}


def test_search_load_embeddings_error_handling(tmp_path):
    """Test error handling when embeddings fail to load."""
    embeddings_path = tmp_path / "nonexistent"

    # Should not crash even if embeddings don't exist
    search = Search(embeddings_path=embeddings_path)
    assert search.general_embeddings is None
    assert search.code_embeddings is None


@patch("rag_core.search.logger")
def test_search_logging(mock_logger, tmp_path):
    """Test that search logs appropriate messages."""
    embeddings_path = tmp_path / "embeddings"
    embeddings_path.mkdir()

    # Should have logged the loading attempt
    mock_logger.info.assert_called()
    mock_logger.error.assert_called()  # Will error because index doesn't exist


def test_search_file_type_integration(tmp_path):
    """Test integration with file type categorization."""
    from rag_core.types import get_file_type_category

    # Test that file type categories work as expected
    assert get_file_type_category("test.py") == "code"
    assert get_file_type_category("README.md") == "mixed"  # Correct expected value

    embeddings_path = tmp_path / "embeddings"
    embeddings_path.mkdir()

    search = Search(embeddings_path=embeddings_path)
    # Should not crash when using file type categories
    assert search is not None


def test_search_defaults(tmp_path):
    """Test Search initialization with minimal parameters."""
    embeddings_path = tmp_path / "embeddings"
    embeddings_path.mkdir()

    search = Search(embeddings_path=embeddings_path)

    # Test defaults
    assert search.use_dual_embedding is False
    assert search.code_model == "microsoft/codebert-base"
    assert search.extension_weights == {}
    assert search.model_weights == {}
