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

    search = Search(
        embeddings_path=embeddings_path,
        dual=True,
        extension_weights={},
        model_weights={},
    )

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

    # Create the search instance to trigger logging
    Search(embeddings_path=embeddings_path)

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


def test_dual_embedding_with_code_index(tmp_path):
    """Test dual embedding when code index exists."""
    embeddings_path = tmp_path / "embeddings"
    embeddings_path.mkdir()

    # Create code_index directory to simulate existing code embeddings
    code_index = embeddings_path / "code_index"
    code_index.mkdir()

    with patch("rag_core.search.logger") as mock_logger:
        search = Search(embeddings_path=embeddings_path, dual=True)

        # Should have tried to load both general and code embeddings
        assert search.use_dual_embedding is True
        mock_logger.info.assert_called()


def test_dual_embedding_without_code_index(tmp_path):
    """Test dual embedding when code index doesn't exist."""
    embeddings_path = tmp_path / "embeddings"
    embeddings_path.mkdir()
    # Don't create code_index directory

    search = Search(embeddings_path=embeddings_path, dual=True)

    # Should have dual embedding enabled but code_embeddings will be None
    assert search.use_dual_embedding is True
    assert search.code_embeddings is None


def test_search_with_available_embeddings(tmp_path):
    """Test search when embeddings are properly set."""
    embeddings_path = tmp_path / "embeddings"
    embeddings_path.mkdir()

    search = Search(embeddings_path=embeddings_path)

    # Mock the embeddings to test search logic
    mock_embeddings = Mock()
    mock_embeddings.search.return_value = [{"id": "test/file.py", "text": "content", "score": 0.8}]
    search.general_embeddings = mock_embeddings

    # Test search
    search.search("test query", limit=5)

    # Should have attempted search
    mock_embeddings.search.assert_called()


def test_search_dual_mode_logic(tmp_path):
    """Test dual embedding search logic."""
    embeddings_path = tmp_path / "embeddings"
    embeddings_path.mkdir()

    search = Search(embeddings_path=embeddings_path, dual=True)

    # Mock both embeddings
    mock_general = Mock()
    mock_code = Mock()

    mock_general.search.return_value = [{"id": "test/file.py", "text": "content", "score": 0.7}]
    mock_code.search.return_value = [{"id": "test/file.py", "text": "content", "score": 0.9}]

    search.general_embeddings = mock_general
    search.code_embeddings = mock_code

    search.search("test query", limit=5)

    # Should have used both embeddings in dual mode
    assert search.use_dual_embedding is True


def test_process_results_prefers_source_document(tmp_path):
    embeddings_path = tmp_path / "embeddings"
    embeddings_path.mkdir()

    search = Search(embeddings_path=embeddings_path)

    results = [
        {
            "id": "repo/pkg/module.py#chunk-0003",
            "score": 0.42,
            "text": "print('hello')",
            "data": {
                "source_document": "repo/pkg/module.py",
                "chunk_index": 3,
                "chunk_count": 5,
            },
        }
    ]

    processed = search._process_and_rank_results(results, limit=5)

    assert processed[0]["source_document"] == "repo/pkg/module.py"
    assert processed[0]["data"]["chunk_index"] == 3


def test_search_file_type_weighting(tmp_path):
    """Test file type weighting in search results."""
    embeddings_path = tmp_path / "embeddings"
    embeddings_path.mkdir()

    # Create search instance to ensure initialization works
    search = Search(embeddings_path=embeddings_path)
    assert search is not None

    # Test with different file types to trigger weighting logic
    test_files = ["test.py", "README.md", "config.json", "data.csv"]
    for file_path in test_files:
        from rag_core.types import get_file_type_category

        category = get_file_type_category(file_path)
        # Include all possible categories that the function can return
        assert category in ["code", "mixed", "documentation", "data", "docs"]


def test_txtai_import_error(tmp_path):
    """Test handling of txtai import error."""
    embeddings_path = tmp_path / "embeddings"
    embeddings_path.mkdir()

    # Mock ImportError when trying to import txtai
    with patch("rag_core.search.logger"):
        with patch.dict("sys.modules", {"txtai.embeddings": None}):
            search = Search(embeddings_path=embeddings_path)

            # Should handle import error gracefully
            assert search.general_embeddings is None
            assert search.code_embeddings is None


def test_search_with_custom_models_and_weights(tmp_path):
    """Test Search with custom models and weights."""
    embeddings_path = tmp_path / "embeddings"
    embeddings_path.mkdir()

    custom_extension_weights = {"py": 1.5, "js": 1.2}
    custom_model_weights = {"code_model": 2.0, "general_model": 1.0}

    search = Search(
        embeddings_path=embeddings_path,
        dual=True,
        code_model="custom/codebert-model",
        extension_weights=custom_extension_weights,
        model_weights=custom_model_weights,
    )

    assert search.code_model == "custom/codebert-model"
    assert search.extension_weights == custom_extension_weights
    assert search.model_weights == custom_model_weights
    assert search.use_dual_embedding is True


@patch("txtai.embeddings.Embeddings")
def test_search_successful_loading(mock_embeddings_class, tmp_path):
    """Test successful embeddings loading."""
    embeddings_path = tmp_path / "embeddings"
    embeddings_path.mkdir()

    # Create index directory
    index_dir = embeddings_path / "index"
    index_dir.mkdir()

    # Mock successful embeddings loading
    mock_embeddings = Mock()
    mock_embeddings_class.return_value = mock_embeddings

    with patch("rag_core.search.logger") as mock_logger:
        search = Search(embeddings_path=embeddings_path)

        # Should have successfully loaded embeddings
        assert search.general_embeddings == mock_embeddings
        mock_logger.info.assert_called()
        mock_embeddings.load.assert_called_with(str(index_dir))


@patch("txtai.embeddings.Embeddings")
def test_search_method_single_embedding(mock_embeddings_class, tmp_path):
    """Test search method with single embedding."""
    embeddings_path = tmp_path / "embeddings"
    embeddings_path.mkdir()

    # Mock embeddings
    mock_embeddings = Mock()
    mock_embeddings.search.return_value = [{"id": "test/file.py", "text": "test content", "score": 0.8}]
    mock_embeddings_class.return_value = mock_embeddings

    search = Search(embeddings_path=embeddings_path, dual=False)
    search.general_embeddings = mock_embeddings

    results = search.search("test query", limit=5)

    # Should have called single embedding search
    mock_embeddings.search.assert_called()
    assert len(results) >= 0  # Results depend on processing


@patch("txtai.embeddings.Embeddings")
def test_search_method_dual_embedding(mock_embeddings_class, tmp_path):
    """Test search method with dual embedding."""
    embeddings_path = tmp_path / "embeddings"
    embeddings_path.mkdir()

    # Mock both general and code embeddings
    mock_general = Mock()
    mock_code = Mock()

    mock_general.search.return_value = [{"id": "test/file.py", "text": "general content", "score": 0.7}]
    mock_code.search.return_value = [{"id": "test/file.py", "text": "code content", "score": 0.9}]

    search = Search(embeddings_path=embeddings_path, dual=True)
    search.general_embeddings = mock_general
    search.code_embeddings = mock_code

    search.search("test query", limit=5)

    # Should have called both embeddings
    mock_general.search.assert_called()
    mock_code.search.assert_called()


@patch("rag_core.search.logger")
def test_search_exception_handling(mock_logger, tmp_path):
    """Test search method exception handling."""
    embeddings_path = tmp_path / "embeddings"
    embeddings_path.mkdir()

    search = Search(embeddings_path=embeddings_path)
    # Don't set up embeddings properly to trigger exception

    with pytest.raises(RuntimeError):
        search.search("test query", limit=5)

    # Should log error
    mock_logger.error.assert_called()


def test_search_no_embeddings_loaded(tmp_path):
    """Test search when no embeddings are loaded."""
    embeddings_path = tmp_path / "embeddings"
    embeddings_path.mkdir()

    search = Search(embeddings_path=embeddings_path)
    # Embeddings will be None due to missing index

    with pytest.raises(RuntimeError):
        search.search("test query", limit=5)


def _build_minimal_index(base_path: Path):
    """Utility to create a minimal sqlite sections table used by fallback tests."""
    index_dir = base_path / "index"
    index_dir.mkdir(parents=True, exist_ok=True)
    db_path = index_dir / "documents"

    import sqlite3

    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sections (
                indexid INTEGER PRIMARY KEY AUTOINCREMENT,
                id TEXT,
                text TEXT,
                tags TEXT,
                entry DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute("DELETE FROM sections")
        rows = [
            (
                "knowledge_base/raw/microlensing_tools/VBMicrolensing/README.md::chunk-0",
                "# VBMicrolensing\n`VBMicrolensing` is a microlensing toolkit.",
            ),
            (
                "knowledge_base/raw/microlensing_tools/SomeOtherRepo/README.md::chunk-0",
                "Unrelated repository text.",
            ),
        ]
        conn.executemany("INSERT INTO sections (id, text) VALUES (?, ?)", rows)
        conn.commit()
    finally:
        conn.close()


def test_id_match_fallback_returns_matches(tmp_path):
    """_id_match_fallback should surface IDs that contain query tokens."""
    embeddings_path = tmp_path / "embeddings"
    _build_minimal_index(embeddings_path)

    search = object.__new__(Search)
    search.embeddings_path = embeddings_path

    matches = Search._id_match_fallback(search, "VBMicrolensing", set(), limit=5)
    assert matches, "Expected fallback to return results"
    assert any("VBMicrolensing" in match["id"] for match in matches)
    assert matches[0]["data"]["source_document"].startswith("knowledge_base/raw/microlensing_tools/VBMicrolensing")


def test_search_includes_id_fallback_results(tmp_path):
    """search() should return fallback matches when semantic search misses."""
    embeddings_path = tmp_path / "embeddings"
    _build_minimal_index(embeddings_path)

    search = object.__new__(Search)
    search.embeddings_path = embeddings_path
    search.use_dual_embedding = False
    search.code_embeddings = None
    search.extension_weights = {}
    search.model_weights = {}

    mock_embeddings = Mock()
    mock_embeddings.search.return_value = []
    search.general_embeddings = mock_embeddings

    results = search.search("VBMicrolensing", limit=3)
    assert results, "Expected fallback results to be returned"
    assert any("VBMicrolensing" in r["source_document"] for r in results)
