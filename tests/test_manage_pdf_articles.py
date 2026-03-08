"""Tests for scripts/manage_pdf_articles.py - PDFArticleManager class."""

import pytest
import yaml
import requests
from pathlib import Path
from unittest.mock import patch, MagicMock

from scripts.manage_pdf_articles import PDFArticleManager


def _write_config(path: Path, config: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(config, f)


@pytest.fixture
def manager(tmp_path):
    return PDFArticleManager(base_path=str(tmp_path / "articles"))


@pytest.fixture
def simple_config():
    return {
        "papers": [
            {"name": "paper-a", "url": "https://example.com/a.pdf", "description": "Paper A"},
            {"name": "paper-b", "url": "https://example.com/b.pdf", "description": "Paper B"},
        ]
    }


# ---------------------------------------------------------------------------
# __init__
# ---------------------------------------------------------------------------


def test_init_creates_base_path(tmp_path):
    base = tmp_path / "deep" / "nested"
    manager = PDFArticleManager(base_path=str(base))
    assert base.exists()


# ---------------------------------------------------------------------------
# load_config / save_config
# ---------------------------------------------------------------------------


def test_load_config_existing(tmp_path, manager, simple_config):
    config_file = tmp_path / "articles.yml"
    _write_config(config_file, simple_config)
    loaded = manager.load_config(str(config_file))
    assert loaded == simple_config


def test_load_config_missing_returns_empty(tmp_path, manager):
    result = manager.load_config(str(tmp_path / "nonexistent.yml"))
    assert result == {}


def test_save_config_roundtrip(tmp_path, manager, simple_config):
    config_file = tmp_path / "out.yml"
    manager.save_config(simple_config, str(config_file))
    assert config_file.exists()
    with open(config_file, "r") as f:
        loaded = yaml.safe_load(f)
    assert loaded["papers"][0]["name"] == "paper-a"


# ---------------------------------------------------------------------------
# download_article
# ---------------------------------------------------------------------------


def _make_response(content=b"PDF content", status_code=200):
    mock = MagicMock()
    mock.status_code = status_code
    mock.raise_for_status = MagicMock()
    mock.iter_content = MagicMock(return_value=[content])
    return mock


def test_download_article_success(tmp_path, manager):
    article_info = {"name": "test-paper", "url": "https://example.com/test.pdf"}
    with patch("scripts.manage_pdf_articles.requests.get", return_value=_make_response()):
        result = manager.download_article(article_info, "papers")
    assert result is True
    assert (manager.base_path / "papers" / "test-paper.pdf").exists()


def test_download_article_skips_existing(tmp_path, manager):
    article_info = {"name": "existing-paper", "url": "https://example.com/existing.pdf"}
    article_path = manager.base_path / "papers" / "existing-paper.pdf"
    article_path.parent.mkdir(parents=True, exist_ok=True)
    article_path.write_bytes(b"existing")

    with patch("scripts.manage_pdf_articles.requests.get") as mock_get:
        result = manager.download_article(article_info, "papers")
    assert result is True
    mock_get.assert_not_called()


def test_download_article_http_error(tmp_path, manager):
    article_info = {"name": "bad-paper", "url": "https://example.com/bad.pdf"}
    mock_resp = MagicMock()
    mock_resp.raise_for_status.side_effect = requests.HTTPError("404")
    with patch("scripts.manage_pdf_articles.requests.get", return_value=mock_resp):
        result = manager.download_article(article_info, "papers")
    assert result is False


def test_download_article_exception_cleanup(tmp_path, manager):
    """Partial download file should be cleaned up on failure."""
    article_info = {"name": "partial-paper", "url": "https://example.com/partial.pdf"}
    with patch("scripts.manage_pdf_articles.requests.get", side_effect=ConnectionError("network error")):
        result = manager.download_article(article_info, "papers")
    assert result is False
    assert not (manager.base_path / "papers" / "partial-paper.pdf").exists()


# ---------------------------------------------------------------------------
# update_article
# ---------------------------------------------------------------------------


def test_update_article_removes_file(tmp_path, manager):
    article_path = manager.base_path / "papers" / "old.pdf"
    article_path.parent.mkdir(parents=True, exist_ok=True)
    article_path.write_bytes(b"old content")

    result = manager.update_article(article_path)
    assert result is True
    assert not article_path.exists()


def test_update_article_handles_missing_file(tmp_path, manager):
    nonexistent = manager.base_path / "papers" / "ghost.pdf"
    result = manager.update_article(nonexistent)
    assert result is False


# ---------------------------------------------------------------------------
# process_category
# ---------------------------------------------------------------------------


def test_process_category_counts_successes(tmp_path, manager, simple_config):
    articles = simple_config["papers"]
    with patch.object(manager, "download_article", side_effect=[True, False]):
        count = manager.process_category("papers", articles)
    assert count == 1


def test_process_category_force_update(tmp_path, manager):
    article_info = {"name": "force-paper", "url": "https://example.com/force.pdf"}
    article_path = manager.base_path / "papers" / "force-paper.pdf"
    article_path.parent.mkdir(parents=True, exist_ok=True)
    article_path.write_bytes(b"old content")

    with (
        patch.object(manager, "update_article", return_value=True) as mock_upd,
        patch.object(manager, "download_article", return_value=True) as mock_dl,
    ):
        count = manager.process_category("papers", [article_info], force_update=True)

    assert count == 1
    mock_upd.assert_called_once()
    mock_dl.assert_called_once()


def test_process_category_force_update_fails(tmp_path, manager):
    article_info = {"name": "fail-paper", "url": "https://example.com/fail.pdf"}
    article_path = manager.base_path / "papers" / "fail-paper.pdf"
    article_path.parent.mkdir(parents=True, exist_ok=True)
    article_path.write_bytes(b"old content")

    with patch.object(manager, "update_article", return_value=False):
        count = manager.process_category("papers", [article_info], force_update=True)
    assert count == 0


# ---------------------------------------------------------------------------
# process_all
# ---------------------------------------------------------------------------


def test_process_all_returns_dict(manager, simple_config):
    with patch.object(manager, "download_article", return_value=True):
        results = manager.process_all(simple_config)
    assert "papers" in results
    assert results["papers"] == 2


def test_process_all_skips_non_list_categories(manager):
    config = {"papers": [{"name": "p", "url": "u", "description": "d"}], "meta": "not-a-list"}
    with patch.object(manager, "download_article", return_value=True):
        results = manager.process_all(config)
    assert "papers" in results
    assert "meta" not in results


# ---------------------------------------------------------------------------
# list_articles
# ---------------------------------------------------------------------------


def test_list_articles_existing(tmp_path, manager, simple_config):
    (manager.base_path / "papers" / "paper-a.pdf").parent.mkdir(parents=True, exist_ok=True)
    (manager.base_path / "papers" / "paper-a.pdf").write_bytes(b"content")
    manager.list_articles(simple_config)  # should not raise


def test_list_articles_skips_non_list(manager):
    config = {"papers": [{"name": "p", "url": "u", "description": "d"}], "meta": "string"}
    manager.list_articles(config)  # should not raise


# ---------------------------------------------------------------------------
# clean_articles
# ---------------------------------------------------------------------------


def test_clean_articles_dry_run(tmp_path, manager, simple_config):
    orphan = manager.base_path / "papers" / "orphan.pdf"
    orphan.parent.mkdir(parents=True, exist_ok=True)
    orphan.write_bytes(b"orphan")
    manager.clean_articles(simple_config, dry_run=True)
    assert orphan.exists()


def test_clean_articles_removes_orphan(tmp_path, manager, simple_config):
    orphan = manager.base_path / "papers" / "orphan.pdf"
    orphan.parent.mkdir(parents=True, exist_ok=True)
    orphan.write_bytes(b"orphan")
    manager.clean_articles(simple_config, dry_run=False)
    assert not orphan.exists()


def test_clean_articles_keeps_configured(tmp_path, manager, simple_config):
    kept = manager.base_path / "papers" / "paper-a.pdf"
    kept.parent.mkdir(parents=True, exist_ok=True)
    kept.write_bytes(b"content")
    manager.clean_articles(simple_config, dry_run=False)
    assert kept.exists()
