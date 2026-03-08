"""Tests for scripts/manage_articles.py - ArticleManager class."""

import sys
import types
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock, call


# ---------------------------------------------------------------------------
# ArticleManager.__init__
# ---------------------------------------------------------------------------

def test_init_creates_articles_path(tmp_path):
    mock_rag = MagicMock()
    mock_textractor_cls = MagicMock(return_value=MagicMock())
    with patch("scripts.manage_articles.RAGService", return_value=mock_rag):
        with patch("scripts.manage_articles.Textractor", mock_textractor_cls):
            with patch("scripts.manage_articles.TXTAI_AVAILABLE", True):
                from scripts.manage_articles import ArticleManager
                manager = ArticleManager(knowledge_base_path=tmp_path)
    articles_path = tmp_path / "raw" / "journal_articles"
    assert articles_path.exists()


def test_init_default_knowledge_base():
    mock_rag = MagicMock()
    mock_textractor_cls = MagicMock(return_value=MagicMock())
    with patch("scripts.manage_articles.RAGService", return_value=mock_rag):
        with patch("scripts.manage_articles.Textractor", mock_textractor_cls):
            with patch("scripts.manage_articles.TXTAI_AVAILABLE", True):
                from scripts.manage_articles import ArticleManager
                manager = ArticleManager()
    assert manager.knowledge_base_path is not None


# ---------------------------------------------------------------------------
# add_article
# ---------------------------------------------------------------------------

def test_add_article_file_not_found(tmp_path):
    mock_rag = MagicMock()
    mock_textractor_instance = MagicMock()
    mock_textractor_cls = MagicMock(return_value=mock_textractor_instance)
    with patch("scripts.manage_articles.RAGService", return_value=mock_rag):
        with patch("scripts.manage_articles.Textractor", mock_textractor_cls):
            with patch("scripts.manage_articles.TXTAI_AVAILABLE", True):
                from scripts.manage_articles import ArticleManager
                manager = ArticleManager(knowledge_base_path=tmp_path)
    result = manager.add_article(tmp_path / "nonexistent.pdf")
    assert result is False


def test_add_article_not_pdf(tmp_path):
    mock_rag = MagicMock()
    mock_textractor_cls = MagicMock(return_value=MagicMock())
    txt_file = tmp_path / "notes.txt"
    txt_file.write_text("some text")
    with patch("scripts.manage_articles.RAGService", return_value=mock_rag):
        with patch("scripts.manage_articles.Textractor", mock_textractor_cls):
            with patch("scripts.manage_articles.TXTAI_AVAILABLE", True):
                from scripts.manage_articles import ArticleManager
                manager = ArticleManager(knowledge_base_path=tmp_path)
    result = manager.add_article(txt_file)
    assert result is False


def test_add_article_too_short_text(tmp_path):
    pdf_file = tmp_path / "short.pdf"
    pdf_file.write_bytes(b"%PDF fake")

    mock_textractor_instance = MagicMock(return_value="short")  # Too short
    mock_rag = MagicMock()
    with patch("scripts.manage_articles.RAGService", return_value=mock_rag):
        with patch("scripts.manage_articles.Textractor", MagicMock(return_value=mock_textractor_instance)):
            with patch("scripts.manage_articles.TXTAI_AVAILABLE", True):
                from scripts.manage_articles import ArticleManager
                manager = ArticleManager(knowledge_base_path=tmp_path)
    result = manager.add_article(pdf_file)
    assert result is False


def test_add_article_success(tmp_path):
    pdf_file = tmp_path / "article.pdf"
    pdf_file.write_bytes(b"%PDF content " * 100)

    long_text = "Extracted article content. " * 200  # Long enough text

    mock_textractor_instance = MagicMock(return_value=long_text)
    mock_rag = MagicMock()
    mock_rag.embeddings = MagicMock()
    mock_rag.embeddings.index = MagicMock()

    with patch("scripts.manage_articles.RAGService", return_value=mock_rag):
        with patch("scripts.manage_articles.Textractor", MagicMock(return_value=mock_textractor_instance)):
            with patch("scripts.manage_articles.TXTAI_AVAILABLE", True):
                with patch("scripts.manage_articles.project_root", tmp_path):
                    from scripts.manage_articles import ArticleManager
                    manager = ArticleManager(knowledge_base_path=tmp_path)
                    result = manager.add_article(pdf_file)
    assert result is True
    mock_rag.embeddings.index.assert_called_once()


def test_add_article_extraction_exception(tmp_path):
    pdf_file = tmp_path / "broken.pdf"
    pdf_file.write_bytes(b"%PDF broken")

    mock_textractor_instance = MagicMock(side_effect=Exception("extraction failed"))
    mock_rag = MagicMock()

    with patch("scripts.manage_articles.RAGService", return_value=mock_rag):
        with patch("scripts.manage_articles.Textractor", MagicMock(return_value=mock_textractor_instance)):
            with patch("scripts.manage_articles.TXTAI_AVAILABLE", True):
                from scripts.manage_articles import ArticleManager
                manager = ArticleManager(knowledge_base_path=tmp_path)

    result = manager.add_article(pdf_file)
    assert result is False


def test_add_article_with_custom_id(tmp_path):
    pdf_file = tmp_path / "article.pdf"
    pdf_file.write_bytes(b"%PDF " * 100)
    long_text = "Long extracted article content. " * 200

    mock_textractor_instance = MagicMock(return_value=long_text)
    mock_rag = MagicMock()
    mock_rag.embeddings = MagicMock()

    with patch("scripts.manage_articles.RAGService", return_value=mock_rag):
        with patch("scripts.manage_articles.Textractor", MagicMock(return_value=mock_textractor_instance)):
            with patch("scripts.manage_articles.TXTAI_AVAILABLE", True):
                with patch("scripts.manage_articles.project_root", tmp_path):
                    from scripts.manage_articles import ArticleManager
                    manager = ArticleManager(knowledge_base_path=tmp_path)
                    result = manager.add_article(pdf_file, article_id="custom/my_article")
    assert result is True


def test_add_article_index_failure(tmp_path):
    pdf_file = tmp_path / "article.pdf"
    pdf_file.write_bytes(b"%PDF " * 100)
    long_text = "Long text. " * 200

    mock_textractor_instance = MagicMock(return_value=long_text)
    mock_rag = MagicMock()
    mock_rag.embeddings.index.side_effect = Exception("DB error")

    with patch("scripts.manage_articles.RAGService", return_value=mock_rag):
        with patch("scripts.manage_articles.Textractor", MagicMock(return_value=mock_textractor_instance)):
            with patch("scripts.manage_articles.TXTAI_AVAILABLE", True):
                from scripts.manage_articles import ArticleManager
                manager = ArticleManager(knowledge_base_path=tmp_path)

    result = manager.add_article(pdf_file)
    assert result is False


# ---------------------------------------------------------------------------
# add_directory
# ---------------------------------------------------------------------------

def test_add_directory_not_found(tmp_path):
    mock_rag = MagicMock()
    with patch("scripts.manage_articles.RAGService", return_value=mock_rag):
        with patch("scripts.manage_articles.Textractor", MagicMock(return_value=MagicMock())):
            with patch("scripts.manage_articles.TXTAI_AVAILABLE", True):
                from scripts.manage_articles import ArticleManager
                manager = ArticleManager(knowledge_base_path=tmp_path)
    count = manager.add_directory(tmp_path / "nonexistent")
    assert count == 0


def test_add_directory_no_pdfs(tmp_path):
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "readme.txt").write_text("not a pdf")

    mock_rag = MagicMock()
    with patch("scripts.manage_articles.RAGService", return_value=mock_rag):
        with patch("scripts.manage_articles.Textractor", MagicMock(return_value=MagicMock())):
            with patch("scripts.manage_articles.TXTAI_AVAILABLE", True):
                from scripts.manage_articles import ArticleManager
                manager = ArticleManager(knowledge_base_path=tmp_path)
    count = manager.add_directory(docs_dir)
    assert count == 0


def test_add_directory_with_pdfs(tmp_path):
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir()
    (docs_dir / "paper1.pdf").write_bytes(b"%PDF content " * 100)
    (docs_dir / "paper2.pdf").write_bytes(b"%PDF content " * 100)

    long_text = "Long extracted text. " * 200
    mock_textractor_instance = MagicMock(return_value=long_text)
    mock_rag = MagicMock()
    mock_rag.embeddings = MagicMock()

    with patch("scripts.manage_articles.RAGService", return_value=mock_rag):
        with patch("scripts.manage_articles.Textractor", MagicMock(return_value=mock_textractor_instance)):
            with patch("scripts.manage_articles.TXTAI_AVAILABLE", True):
                with patch("scripts.manage_articles.project_root", tmp_path):
                    from scripts.manage_articles import ArticleManager
                    manager = ArticleManager(knowledge_base_path=tmp_path)
                    count = manager.add_directory(docs_dir)
    assert count == 2


# ---------------------------------------------------------------------------
# list_articles
# ---------------------------------------------------------------------------

def test_list_articles_success(tmp_path):
    mock_rag = MagicMock()
    mock_rag.embeddings.database.search.return_value = [
        {"id": "journal_articles/paper1", "text": "Long article text " * 10},
        {"id": "journal_articles/paper2", "text": "Another article " * 10},
    ]

    with patch("scripts.manage_articles.RAGService", return_value=mock_rag):
        with patch("scripts.manage_articles.Textractor", MagicMock(return_value=MagicMock())):
            with patch("scripts.manage_articles.TXTAI_AVAILABLE", True):
                from scripts.manage_articles import ArticleManager
                manager = ArticleManager(knowledge_base_path=tmp_path)

    articles = manager.list_articles()
    assert len(articles) == 2
    assert articles[0]["id"] == "journal_articles/paper1"


def test_list_articles_exception(tmp_path):
    mock_rag = MagicMock()
    mock_rag.embeddings.database.search.side_effect = Exception("DB error")

    with patch("scripts.manage_articles.RAGService", return_value=mock_rag):
        with patch("scripts.manage_articles.Textractor", MagicMock(return_value=MagicMock())):
            with patch("scripts.manage_articles.TXTAI_AVAILABLE", True):
                from scripts.manage_articles import ArticleManager
                manager = ArticleManager(knowledge_base_path=tmp_path)

    articles = manager.list_articles()
    assert articles == []


# ---------------------------------------------------------------------------
# remove_article
# ---------------------------------------------------------------------------

def test_remove_article_not_found(tmp_path):
    mock_rag = MagicMock()
    mock_rag.embeddings.database.search.return_value = []

    with patch("scripts.manage_articles.RAGService", return_value=mock_rag):
        with patch("scripts.manage_articles.Textractor", MagicMock(return_value=MagicMock())):
            with patch("scripts.manage_articles.TXTAI_AVAILABLE", True):
                from scripts.manage_articles import ArticleManager
                manager = ArticleManager(knowledge_base_path=tmp_path)

    result = manager.remove_article("journal_articles/nonexistent")
    assert result is False


def test_remove_article_success(tmp_path):
    mock_rag = MagicMock()
    mock_rag.embeddings.database.search.return_value = [
        {"id": "journal_articles/test_paper"}
    ]
    mock_rag.embeddings.delete = MagicMock()

    with patch("scripts.manage_articles.RAGService", return_value=mock_rag):
        with patch("scripts.manage_articles.Textractor", MagicMock(return_value=MagicMock())):
            with patch("scripts.manage_articles.TXTAI_AVAILABLE", True):
                from scripts.manage_articles import ArticleManager
                manager = ArticleManager(knowledge_base_path=tmp_path)

    result = manager.remove_article("journal_articles/test_paper")
    assert result is True
    mock_rag.embeddings.delete.assert_called_once_with(["journal_articles/test_paper"])


def test_remove_article_with_physical_file(tmp_path):
    mock_rag = MagicMock()
    mock_rag.embeddings.database.search.return_value = [{"id": "journal_articles/test_paper"}]
    mock_rag.embeddings.delete = MagicMock()

    with patch("scripts.manage_articles.RAGService", return_value=mock_rag):
        with patch("scripts.manage_articles.Textractor", MagicMock(return_value=MagicMock())):
            with patch("scripts.manage_articles.TXTAI_AVAILABLE", True):
                from scripts.manage_articles import ArticleManager
                manager = ArticleManager(knowledge_base_path=tmp_path)

    # Create the physical file
    pdf_file = manager.articles_path / "test_paper.pdf"
    pdf_file.write_bytes(b"fake pdf")

    result = manager.remove_article("journal_articles/test_paper")
    assert result is True
    assert not pdf_file.exists()


def test_remove_article_exception(tmp_path):
    mock_rag = MagicMock()
    mock_rag.embeddings.database.search.side_effect = Exception("DB error")

    with patch("scripts.manage_articles.RAGService", return_value=mock_rag):
        with patch("scripts.manage_articles.Textractor", MagicMock(return_value=MagicMock())):
            with patch("scripts.manage_articles.TXTAI_AVAILABLE", True):
                from scripts.manage_articles import ArticleManager
                manager = ArticleManager(knowledge_base_path=tmp_path)

    result = manager.remove_article("journal_articles/bad")
    assert result is False


# ---------------------------------------------------------------------------
# rebuild_index
# ---------------------------------------------------------------------------

def test_rebuild_index_returns_false(tmp_path):
    mock_rag = MagicMock()
    with patch("scripts.manage_articles.RAGService", return_value=mock_rag):
        with patch("scripts.manage_articles.Textractor", MagicMock(return_value=MagicMock())):
            with patch("scripts.manage_articles.TXTAI_AVAILABLE", True):
                from scripts.manage_articles import ArticleManager
                manager = ArticleManager(knowledge_base_path=tmp_path)

    result = manager.rebuild_index()
    assert result is False


# ---------------------------------------------------------------------------
# _confirm helper
# ---------------------------------------------------------------------------

def test_confirm_yes(tmp_path, monkeypatch):
    mock_rag = MagicMock()
    with patch("scripts.manage_articles.RAGService", return_value=mock_rag):
        with patch("scripts.manage_articles.Textractor", MagicMock(return_value=MagicMock())):
            with patch("scripts.manage_articles.TXTAI_AVAILABLE", True):
                from scripts.manage_articles import ArticleManager
                manager = ArticleManager(knowledge_base_path=tmp_path)

    monkeypatch.setattr("builtins.input", lambda _: "y")
    assert manager._confirm("Are you sure?") is True


def test_confirm_no(tmp_path, monkeypatch):
    mock_rag = MagicMock()
    with patch("scripts.manage_articles.RAGService", return_value=mock_rag):
        with patch("scripts.manage_articles.Textractor", MagicMock(return_value=MagicMock())):
            with patch("scripts.manage_articles.TXTAI_AVAILABLE", True):
                from scripts.manage_articles import ArticleManager
                manager = ArticleManager(knowledge_base_path=tmp_path)

    monkeypatch.setattr("builtins.input", lambda _: "n")
    assert manager._confirm("Are you sure?") is False


# ---------------------------------------------------------------------------
# Additional tests for improved coverage
# ---------------------------------------------------------------------------

def test_add_article_existing_dest_decline(tmp_path, monkeypatch):
    """When article already exists and user declines overwrite, return False."""
    pdf_file = tmp_path / "article.pdf"
    pdf_file.write_bytes(b"%PDF content " * 100)
    long_text = "Long extracted text. " * 200

    mock_textractor_instance = MagicMock(return_value=long_text)
    mock_rag = MagicMock()

    with patch("scripts.manage_articles.RAGService", return_value=mock_rag):
        with patch("scripts.manage_articles.Textractor", MagicMock(return_value=mock_textractor_instance)):
            with patch("scripts.manage_articles.TXTAI_AVAILABLE", True):
                with patch("scripts.manage_articles.project_root", tmp_path):
                    from scripts.manage_articles import ArticleManager
                    manager = ArticleManager(knowledge_base_path=tmp_path)
                    # Pre-create the destination file
                    dest = manager.articles_path / pdf_file.name
                    dest.write_bytes(b"existing")
                    monkeypatch.setattr("builtins.input", lambda _: "n")
                    result = manager.add_article(pdf_file)
    assert result is False


def test_add_article_existing_dest_accept(tmp_path, monkeypatch):
    """When article already exists and user accepts overwrite, continue."""
    pdf_file = tmp_path / "article.pdf"
    pdf_file.write_bytes(b"%PDF content " * 100)
    long_text = "Long extracted text. " * 200

    mock_textractor_instance = MagicMock(return_value=long_text)
    mock_rag = MagicMock()
    mock_rag.embeddings = MagicMock()

    with patch("scripts.manage_articles.RAGService", return_value=mock_rag):
        with patch("scripts.manage_articles.Textractor", MagicMock(return_value=mock_textractor_instance)):
            with patch("scripts.manage_articles.TXTAI_AVAILABLE", True):
                with patch("scripts.manage_articles.project_root", tmp_path):
                    from scripts.manage_articles import ArticleManager
                    manager = ArticleManager(knowledge_base_path=tmp_path)
                    # Pre-create the destination file
                    dest = manager.articles_path / pdf_file.name
                    dest.write_bytes(b"existing")
                    monkeypatch.setattr("builtins.input", lambda _: "y")
                    result = manager.add_article(pdf_file)
    assert result is True


def test_add_article_index_failure_cleanup(tmp_path):
    """When indexing fails, the copied file should be cleaned up."""
    pdf_file = tmp_path / "article.pdf"
    pdf_file.write_bytes(b"%PDF content " * 100)
    long_text = "Long extracted text. " * 200

    mock_textractor_instance = MagicMock(return_value=long_text)
    mock_rag = MagicMock()
    mock_rag.embeddings.index.side_effect = Exception("index error")

    with patch("scripts.manage_articles.RAGService", return_value=mock_rag):
        with patch("scripts.manage_articles.Textractor", MagicMock(return_value=mock_textractor_instance)):
            with patch("scripts.manage_articles.TXTAI_AVAILABLE", True):
                with patch("scripts.manage_articles.project_root", tmp_path):
                    from scripts.manage_articles import ArticleManager
                    manager = ArticleManager(knowledge_base_path=tmp_path)
                    result = manager.add_article(pdf_file)
    assert result is False
    # Copied file should be cleaned up
    dest = manager.articles_path / pdf_file.name
    assert not dest.exists()


def test_main_no_command(tmp_path, monkeypatch):
    """main() with no command prints help and returns."""
    monkeypatch.setattr("sys.argv", ["manage_articles.py"])
    mock_rag = MagicMock()
    with patch("scripts.manage_articles.RAGService", return_value=mock_rag):
        with patch("scripts.manage_articles.Textractor", MagicMock(return_value=MagicMock())):
            with patch("scripts.manage_articles.TXTAI_AVAILABLE", True):
                from scripts.manage_articles import main
                # Should not raise
                main()


def test_main_list_command(tmp_path, monkeypatch):
    """main() list command shows articles."""
    monkeypatch.setattr("sys.argv", ["manage_articles.py", "list"])
    mock_rag = MagicMock()
    mock_rag.embeddings.database.search.return_value = []

    with patch("scripts.manage_articles.RAGService", return_value=mock_rag):
        with patch("scripts.manage_articles.Textractor", MagicMock(return_value=MagicMock())):
            with patch("scripts.manage_articles.TXTAI_AVAILABLE", True):
                from scripts.manage_articles import main, ArticleManager
                main()


def test_main_rebuild_command(tmp_path, monkeypatch):
    """main() rebuild command."""
    monkeypatch.setattr("sys.argv", ["manage_articles.py", "rebuild"])
    mock_rag = MagicMock()
    with patch("scripts.manage_articles.RAGService", return_value=mock_rag):
        with patch("scripts.manage_articles.Textractor", MagicMock(return_value=MagicMock())):
            with patch("scripts.manage_articles.TXTAI_AVAILABLE", True):
                from scripts.manage_articles import main
                with pytest.raises(SystemExit):
                    main()


def test_main_remove_command(tmp_path, monkeypatch):
    """main() remove command when article not found."""
    monkeypatch.setattr("sys.argv", ["manage_articles.py", "remove", "journal_articles/nonexistent"])
    mock_rag = MagicMock()
    mock_rag.embeddings.database.search.return_value = []
    with patch("scripts.manage_articles.RAGService", return_value=mock_rag):
        with patch("scripts.manage_articles.Textractor", MagicMock(return_value=MagicMock())):
            with patch("scripts.manage_articles.TXTAI_AVAILABLE", True):
                from scripts.manage_articles import main
                with pytest.raises(SystemExit):
                    main()


def test_main_add_command(tmp_path, monkeypatch):
    """main() add command with nonexistent file."""
    monkeypatch.setattr("sys.argv", ["manage_articles.py", "add", str(tmp_path / "nonexistent.pdf")])
    mock_rag = MagicMock()
    with patch("scripts.manage_articles.RAGService", return_value=mock_rag):
        with patch("scripts.manage_articles.Textractor", MagicMock(return_value=MagicMock())):
            with patch("scripts.manage_articles.TXTAI_AVAILABLE", True):
                from scripts.manage_articles import main
                with pytest.raises(SystemExit):
                    main()
