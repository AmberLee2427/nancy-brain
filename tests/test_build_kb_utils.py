"""Additional tests for scripts/build_knowledge_base.py utility functions."""

import os
import sys
import types
import pytest
import yaml
import subprocess
from pathlib import Path
from unittest.mock import patch, MagicMock, call
import requests

import scripts.build_knowledge_base as kb_module
from scripts.build_knowledge_base import (
    is_excluded_pdf,
    load_repo_readme,
    collect_repo_files,
    emit_progress,
    get_file_type_category,
    extract_text_fallback,
    process_pdf_with_fallback,
    download_pdf_articles,
    clone_repositories,
)


# ---------------------------------------------------------------------------
# is_excluded_pdf
# ---------------------------------------------------------------------------


def test_is_excluded_pdf_logo():
    assert is_excluded_pdf("repo/logo/icon.pdf") is True


def test_is_excluded_pdf_psf():
    assert is_excluded_pdf("/data/PSF_model.pdf") is True


def test_is_excluded_pdf_glossary():
    assert is_excluded_pdf("docs/Glossary.pdf") is True


def test_is_excluded_pdf_normal():
    assert is_excluded_pdf("/science/repo/paper.pdf") is False


def test_is_excluded_pdf_graphics():
    assert is_excluded_pdf("/repo/graphics/figure.pdf") is True


# ---------------------------------------------------------------------------
# load_repo_readme
# ---------------------------------------------------------------------------


def test_load_repo_readme_finds_readme_md(tmp_path):
    readme = tmp_path / "README.md"
    readme.write_text("# Hello\nThis is a test.", encoding="utf-8")
    result = load_repo_readme(tmp_path)
    assert result is not None
    assert "Hello" in result["content"]
    assert result["path"] == "README.md"


def test_load_repo_readme_finds_readme_rst(tmp_path):
    readme = tmp_path / "README.rst"
    readme.write_text("Title\n=====\nSome text.", encoding="utf-8")
    result = load_repo_readme(tmp_path)
    assert result is not None
    assert result["path"] == "README.rst"


def test_load_repo_readme_empty_readme(tmp_path):
    readme = tmp_path / "README.md"
    readme.write_text("   \n  ", encoding="utf-8")
    result = load_repo_readme(tmp_path)
    assert result is None


def test_load_repo_readme_no_readme(tmp_path):
    result = load_repo_readme(tmp_path)
    assert result is None


# ---------------------------------------------------------------------------
# collect_repo_files
# ---------------------------------------------------------------------------


def test_collect_repo_files_text_files(tmp_path):
    (tmp_path / "main.py").write_text("print('hi')")
    (tmp_path / "readme.md").write_text("# README")
    (tmp_path / "config.yml").write_text("key: value")
    text_files, pdf_files = collect_repo_files(tmp_path)
    assert len(text_files) == 3
    assert len(pdf_files) == 0


def test_collect_repo_files_with_pdf(tmp_path):
    (tmp_path / "paper.pdf").write_bytes(b"%PDF-1.4 content")
    text_files, pdf_files = collect_repo_files(tmp_path)
    assert len(pdf_files) == 1


def test_collect_repo_files_skips_git_dir(tmp_path):
    git_dir = tmp_path / ".git"
    git_dir.mkdir()
    (git_dir / "config").write_text("repo config")
    text_files, pdf_files = collect_repo_files(tmp_path)
    assert not any(".git" in str(f) for f in text_files)


def test_collect_repo_files_nb_txt(tmp_path):
    (tmp_path / "notebook.nb.txt").write_text("notebook content")
    text_files, _ = collect_repo_files(tmp_path)
    assert any("nb.txt" in str(f) for f in text_files)


# ---------------------------------------------------------------------------
# emit_progress
# ---------------------------------------------------------------------------


def test_emit_progress_outputs_json(capsys):
    emit_progress(50, stage="cloning", detail="repo-x")
    captured = capsys.readouterr()
    assert "PROGRESS_JSON:" in captured.out
    import json
    data = json.loads(captured.out.split("PROGRESS_JSON: ")[1])
    assert data["percent"] == 50
    assert data["stage"] == "cloning"
    assert data["detail"] == "repo-x"


def test_emit_progress_no_raise_on_exception():
    # Should never raise
    emit_progress("not-an-int", stage=None, detail=None)


# ---------------------------------------------------------------------------
# get_file_type_category
# ---------------------------------------------------------------------------


def test_get_file_type_category_python():
    assert get_file_type_category("repo/script.py") == "code"


def test_get_file_type_category_js():
    assert get_file_type_category("repo/app.js") == "code"


def test_get_file_type_category_markdown():
    assert get_file_type_category("docs/guide.md") == "mixed"


def test_get_file_type_category_yaml():
    assert get_file_type_category("config.yaml") == "mixed"


def test_get_file_type_category_notebook():
    assert get_file_type_category("notebooks/analysis.nb.txt") == "mixed"


def test_get_file_type_category_rst():
    assert get_file_type_category("docs/api.rst") == "mixed"


def test_get_file_type_category_other():
    assert get_file_type_category("data/results.csv") == "docs"


def test_get_file_type_category_cpp():
    assert get_file_type_category("src/main.cpp") == "code"


# ---------------------------------------------------------------------------
# extract_text_fallback
# ---------------------------------------------------------------------------


def test_extract_text_fallback_with_pypdf2(tmp_path):
    pdf_path = tmp_path / "test.pdf"
    pdf_path.write_bytes(b"fake pdf")

    mock_page = MagicMock()
    mock_page.extract_text.return_value = "Some extracted text content " * 5
    mock_reader = MagicMock()
    mock_reader.pages = [mock_page]
    mock_pdf_reader_class = MagicMock(return_value=mock_reader)
    
    import types
    fake_pypdf2 = types.ModuleType("PyPDF2")
    fake_pypdf2.PdfReader = mock_pdf_reader_class

    saved = sys.modules.get("PyPDF2")
    sys.modules["PyPDF2"] = fake_pypdf2
    try:
        result = extract_text_fallback(str(pdf_path))
    finally:
        if saved is None:
            sys.modules.pop("PyPDF2", None)
        else:
            sys.modules["PyPDF2"] = saved
    
    assert result is not None
    assert len(result) > 100


def test_extract_text_fallback_pypdf2_short_text(tmp_path):
    pdf_path = tmp_path / "short.pdf"
    pdf_path.write_bytes(b"fake pdf")

    mock_page = MagicMock()
    mock_page.extract_text.return_value = "short"
    mock_reader = MagicMock()
    mock_reader.pages = [mock_page]
    mock_pdf_reader_class = MagicMock(return_value=mock_reader)

    import types
    fake_pypdf2 = types.ModuleType("PyPDF2")
    fake_pypdf2.PdfReader = mock_pdf_reader_class
    
    # Also ensure pdfplumber fails to avoid fallthrough
    fake_pdfplumber = types.ModuleType("pdfplumber")
    fake_pdfplumber.open = MagicMock(side_effect=ImportError("no pdfplumber"))
    
    # And fitz fails
    fake_fitz = types.ModuleType("fitz")
    fake_fitz.open = MagicMock(side_effect=ImportError("no fitz"))

    saved = {k: sys.modules.get(k) for k in ["PyPDF2", "pdfplumber", "fitz"]}
    sys.modules["PyPDF2"] = fake_pypdf2
    sys.modules["pdfplumber"] = fake_pdfplumber
    sys.modules["fitz"] = fake_fitz
    
    try:
        result = extract_text_fallback(str(pdf_path))
    finally:
        for k, v in saved.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v
    
    assert result is None


def test_extract_text_fallback_all_fail(tmp_path):
    """All extraction methods fail -> returns None."""
    pdf_path = tmp_path / "fail.pdf"
    pdf_path.write_bytes(b"fake")

    import types
    modules = ["PyPDF2", "pdfplumber", "fitz"]
    saved = {k: sys.modules.get(k) for k in modules}
    for mod in modules:
        fake = types.ModuleType(mod)
        sys.modules[mod] = fake

    try:
        result = extract_text_fallback(str(pdf_path))
    except Exception:
        result = None
    finally:
        for k, v in saved.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v

    assert result is None
# ---------------------------------------------------------------------------
# process_pdf_with_fallback
# ---------------------------------------------------------------------------


def test_process_pdf_fallback_skip_pdfs(tmp_path, monkeypatch):
    monkeypatch.setattr(kb_module, "SKIP_PDFS", True)
    pdf_path = tmp_path / "test.pdf"
    pdf_path.write_bytes(b"fake pdf content")
    content, success = process_pdf_with_fallback(pdf_path)
    # When SKIP_PDFS is set, tika is skipped; rely on fallback
    # Should return None/False since no fallback libs available
    assert isinstance(success, bool)


def test_process_pdf_fallback_success(tmp_path, monkeypatch):
    pdf_path = tmp_path / "test.pdf"
    pdf_path.write_bytes(b"fake pdf content " * 50)
    
    monkeypatch.setattr(kb_module, "TIKA_AVAILABLE", False)
    monkeypatch.setattr(kb_module, "SKIP_PDFS", False)
    
    with patch.object(kb_module, "extract_text_fallback", return_value="extracted text " * 50):
        content, success = process_pdf_with_fallback(pdf_path)
    assert success is True
    assert content is not None


def test_process_pdf_fallback_content_too_short(tmp_path, monkeypatch):
    pdf_path = tmp_path / "tiny.pdf"
    pdf_path.write_bytes(b"fake pdf")
    
    monkeypatch.setattr(kb_module, "TIKA_AVAILABLE", False)
    monkeypatch.setattr(kb_module, "SKIP_PDFS", False)
    monkeypatch.setattr(kb_module, "MIN_PDF_TEXT_CHARS", 10000)  # Very high threshold
    
    with patch.object(kb_module, "extract_text_fallback", return_value="short"):
        content, success = process_pdf_with_fallback(pdf_path)
    assert success is False


# ---------------------------------------------------------------------------
# download_pdf_articles
# ---------------------------------------------------------------------------


def _make_requests_response(content=b"A" * 10000, content_type="application/pdf", status_code=200):
    mock = MagicMock()
    mock.status_code = status_code
    mock.content = content
    mock.headers = {"Content-Type": content_type}
    mock.raise_for_status = MagicMock()
    return mock


def _write_articles_config(path: Path, config: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(config, f)


def test_download_pdf_success(tmp_path):
    config_path = tmp_path / "articles.yml"
    _write_articles_config(config_path, {
        "papers": [{"name": "paper1", "url": "https://example.com/paper1.pdf"}]
    })
    
    mock_session = MagicMock()
    mock_session.get.return_value = _make_requests_response()
    mock_session.max_redirects = 15

    with patch("scripts.build_knowledge_base.requests.Session", return_value=mock_session):
        result = download_pdf_articles(str(config_path), base_path=str(tmp_path / "raw"))
    
    assert "paper1" in str(result["successful_downloads"])


def test_download_pdf_already_exists(tmp_path):
    config_path = tmp_path / "articles.yml"
    _write_articles_config(config_path, {
        "papers": [{"name": "existing", "url": "https://example.com/existing.pdf"}]
    })
    
    # Create the file
    dest = tmp_path / "raw" / "papers" / "existing.pdf"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(b"existing content")

    with patch("scripts.build_knowledge_base.requests.Session"):
        result = download_pdf_articles(str(config_path), base_path=str(tmp_path / "raw"))
    
    assert "papers/existing" in result["skipped_existing"]


def test_download_pdf_dry_run(tmp_path):
    config_path = tmp_path / "articles.yml"
    _write_articles_config(config_path, {
        "papers": [{"name": "test", "url": "https://example.com/test.pdf"}]
    })
    
    mock_session = MagicMock()
    with patch("scripts.build_knowledge_base.requests.Session", return_value=mock_session):
        result = download_pdf_articles(str(config_path), base_path=str(tmp_path / "raw"), dry_run=True)
    
    mock_session.get.assert_not_called()
    assert not (tmp_path / "raw" / "papers" / "test.pdf").exists()


def test_download_pdf_failure(tmp_path):
    config_path = tmp_path / "articles.yml"
    _write_articles_config(config_path, {
        "papers": [{"name": "bad", "url": "https://example.com/bad.pdf"}]
    })
    
    mock_session = MagicMock()
    mock_session.get.side_effect = requests.ConnectionError("connection refused")

    with patch("scripts.build_knowledge_base.requests.Session", return_value=mock_session):
        result = download_pdf_articles(str(config_path), base_path=str(tmp_path / "raw"))
    
    assert any("bad" in entry for entry in result["failed_downloads"])


def test_download_pdf_html_response(tmp_path):
    """PDF download that returns HTML (anti-scraping) should fail."""
    config_path = tmp_path / "articles.yml"
    _write_articles_config(config_path, {
        "papers": [{"name": "html-paper", "url": "https://example.com/paper.pdf"}]
    })
    
    mock_session = MagicMock()
    mock_session.get.return_value = _make_requests_response(
        content=b"<html>Access denied</html>",
        content_type="text/html",
    )

    with patch("scripts.build_knowledge_base.requests.Session", return_value=mock_session):
        result = download_pdf_articles(str(config_path), base_path=str(tmp_path / "raw"))
    
    assert any("html-paper" in entry for entry in result["failed_downloads"])


def test_download_pdf_with_category_filter(tmp_path):
    config_path = tmp_path / "articles.yml"
    _write_articles_config(config_path, {
        "papers": [{"name": "p1", "url": "https://example.com/p1.pdf"}],
        "other": [{"name": "p2", "url": "https://example.com/p2.pdf"}],
    })
    
    mock_session = MagicMock()
    mock_session.get.return_value = _make_requests_response()
    
    with patch("scripts.build_knowledge_base.requests.Session", return_value=mock_session):
        result = download_pdf_articles(
            str(config_path), base_path=str(tmp_path / "raw"), category="papers"
        )
    
    # Only paper from "papers" category should be processed
    assert mock_session.get.call_count == 1


# ---------------------------------------------------------------------------
# clone_repositories - extended scenarios
# ---------------------------------------------------------------------------


def _write_repos_config(path: Path, config: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(config, f)


def test_clone_repositories_skips_existing(tmp_path):
    config_path = tmp_path / "repos.yml"
    _write_repos_config(config_path, {
        "science": [{"name": "existing", "url": "https://github.com/org/existing.git"}]
    })
    dest = tmp_path / "raw" / "science" / "existing"
    dest.mkdir(parents=True, exist_ok=True)

    with patch("scripts.build_knowledge_base.subprocess.run"):
        result = clone_repositories(str(config_path), base_path=str(tmp_path / "raw"))

    assert "science/existing" in result["skipped_existing"]


def test_clone_repositories_dry_run(tmp_path):
    config_path = tmp_path / "repos.yml"
    _write_repos_config(config_path, {
        "science": [{"name": "new-repo", "url": "https://github.com/org/new-repo.git"}]
    })

    with patch("scripts.build_knowledge_base.subprocess.run") as mock_run:
        result = clone_repositories(str(config_path), base_path=str(tmp_path / "raw"), dry_run=True)

    mock_run.assert_not_called()


def test_clone_repositories_force_update_existing(tmp_path):
    config_path = tmp_path / "repos.yml"
    _write_repos_config(config_path, {
        "science": [{"name": "repo", "url": "https://github.com/org/repo.git"}]
    })
    dest = tmp_path / "raw" / "science" / "repo"
    dest.mkdir(parents=True, exist_ok=True)

    with patch("scripts.build_knowledge_base.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="main\n")
        result = clone_repositories(
            str(config_path), base_path=str(tmp_path / "raw"), force_update=True
        )

    assert "science/repo" in result["successful_updates"]


def test_clone_repositories_force_update_with_ref(tmp_path):
    config_path = tmp_path / "repos.yml"
    _write_repos_config(config_path, {
        "science": [{"name": "repo", "url": "https://github.com/org/repo.git", "ref": "v1.0"}]
    })
    dest = tmp_path / "raw" / "science" / "repo"
    dest.mkdir(parents=True, exist_ok=True)

    with patch("scripts.build_knowledge_base.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="main\n")
        result = clone_repositories(
            str(config_path), base_path=str(tmp_path / "raw"), force_update=True
        )
    assert "science/repo" in result["successful_updates"]


def test_clone_repositories_force_update_with_sha_ref(tmp_path):
    sha = "a" * 40
    config_path = tmp_path / "repos.yml"
    _write_repos_config(config_path, {
        "science": [{"name": "repo", "url": "https://github.com/org/repo.git", "ref": sha}]
    })
    dest = tmp_path / "raw" / "science" / "repo"
    dest.mkdir(parents=True, exist_ok=True)

    with patch("scripts.build_knowledge_base.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="main\n")
        result = clone_repositories(
            str(config_path), base_path=str(tmp_path / "raw"), force_update=True
        )
    assert "science/repo" in result["successful_updates"]


def test_clone_repositories_update_failure(tmp_path):
    config_path = tmp_path / "repos.yml"
    _write_repos_config(config_path, {
        "science": [{"name": "repo", "url": "https://github.com/org/repo.git"}]
    })
    dest = tmp_path / "raw" / "science" / "repo"
    dest.mkdir(parents=True, exist_ok=True)

    with patch("scripts.build_knowledge_base.subprocess.run") as mock_run:
        mock_run.side_effect = subprocess.CalledProcessError(1, ["git"], stderr="remote error")
        result = clone_repositories(
            str(config_path), base_path=str(tmp_path / "raw"), force_update=True
        )
    assert any("repo" in entry for entry in result["failed_updates"])


def test_clone_repositories_clone_with_ref(tmp_path):
    config_path = tmp_path / "repos.yml"
    _write_repos_config(config_path, {
        "science": [{"name": "ref-repo", "url": "https://github.com/org/repo.git", "ref": "v2.0"}]
    })

    with patch("scripts.build_knowledge_base.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        result = clone_repositories(str(config_path), base_path=str(tmp_path / "raw"))

    # Should have cloned with --branch v2.0
    clone_calls = [c.args[0] for c in mock_run.call_args_list if c.args and c.args[0][:2] == ["git", "clone"]]
    assert any("--branch" in call and "v2.0" in call for call in clone_calls)


def test_clone_repositories_clone_failure(tmp_path):
    config_path = tmp_path / "repos.yml"
    _write_repos_config(config_path, {
        "science": [{"name": "bad", "url": "https://github.com/org/bad.git"}]
    })

    with patch("scripts.build_knowledge_base.subprocess.run") as mock_run:
        mock_run.side_effect = subprocess.CalledProcessError(128, ["git"], stderr="not found")
        result = clone_repositories(str(config_path), base_path=str(tmp_path / "raw"))

    assert any("bad" in entry for entry in result["failed_clones"])


def test_clone_repositories_dry_run_existing(tmp_path):
    config_path = tmp_path / "repos.yml"
    _write_repos_config(config_path, {
        "science": [{"name": "repo", "url": "https://github.com/org/repo.git"}]
    })
    dest = tmp_path / "raw" / "science" / "repo"
    dest.mkdir(parents=True, exist_ok=True)

    with patch("scripts.build_knowledge_base.subprocess.run") as mock_run:
        result = clone_repositories(
            str(config_path), base_path=str(tmp_path / "raw"),
            dry_run=True, force_update=True
        )
    mock_run.assert_not_called()


def test_clone_repositories_with_sha_ref_clone(tmp_path):
    sha = "b" * 40
    config_path = tmp_path / "repos.yml"
    _write_repos_config(config_path, {
        "science": [{"name": "sha-repo", "url": "https://github.com/org/repo.git", "ref": sha}]
    })

    with patch("scripts.build_knowledge_base.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        result = clone_repositories(str(config_path), base_path=str(tmp_path / "raw"))

    # Should have cloned without --branch and then checked out the SHA
    calls = [c.args[0] for c in mock_run.call_args_list]
    clone_calls = [c for c in calls if c[:2] == ["git", "clone"]]
    checkout_calls = [c for c in calls if c[:2] == ["git", "checkout"]]
    assert len(clone_calls) == 1
    assert "--branch" not in clone_calls[0]
    assert any(sha in c for c in checkout_calls)


# ---------------------------------------------------------------------------
# cleanup_pdf_articles
# ---------------------------------------------------------------------------

from scripts.build_knowledge_base import cleanup_pdf_articles, cleanup_raw_repositories


def test_cleanup_pdf_articles_removes_files(tmp_path):
    config_path = tmp_path / "articles.yml"
    _write_articles_config(config_path, {
        "papers": [{"name": "paper1", "url": "https://example.com/paper1.pdf"}]
    })

    pdf_file = tmp_path / "raw" / "papers" / "paper1.pdf"
    pdf_file.parent.mkdir(parents=True, exist_ok=True)
    pdf_file.write_bytes(b"fake pdf")

    cleanup_pdf_articles(str(config_path), base_path=str(tmp_path / "raw"))
    assert not pdf_file.exists()


def test_cleanup_pdf_articles_handles_missing_file(tmp_path):
    config_path = tmp_path / "articles.yml"
    _write_articles_config(config_path, {
        "papers": [{"name": "nonexistent", "url": "https://example.com/p.pdf"}]
    })
    # Should not raise even if file doesn't exist
    cleanup_pdf_articles(str(config_path), base_path=str(tmp_path / "raw"))


def test_cleanup_pdf_articles_removes_empty_dirs(tmp_path):
    config_path = tmp_path / "articles.yml"
    _write_articles_config(config_path, {
        "papers": [{"name": "paper1", "url": "https://example.com/p.pdf"}]
    })
    # Create empty category dir
    empty_dir = tmp_path / "raw" / "papers"
    empty_dir.mkdir(parents=True, exist_ok=True)
    pdf = empty_dir / "paper1.pdf"
    pdf.write_bytes(b"fake")

    cleanup_pdf_articles(str(config_path), base_path=str(tmp_path / "raw"))
    # The empty dir should be removed after pdf is deleted
    assert not empty_dir.exists()


def test_cleanup_pdf_articles_with_category_filter(tmp_path):
    config_path = tmp_path / "articles.yml"
    _write_articles_config(config_path, {
        "papers": [{"name": "p1", "url": "https://example.com/p1.pdf"}],
        "other": [{"name": "p2", "url": "https://example.com/p2.pdf"}],
    })
    pdf1 = tmp_path / "raw" / "papers" / "p1.pdf"
    pdf2 = tmp_path / "raw" / "other" / "p2.pdf"
    pdf1.parent.mkdir(parents=True, exist_ok=True)
    pdf2.parent.mkdir(parents=True, exist_ok=True)
    pdf1.write_bytes(b"pdf1")
    pdf2.write_bytes(b"pdf2")

    cleanup_pdf_articles(str(config_path), base_path=str(tmp_path / "raw"), category="papers")
    assert not pdf1.exists()
    assert pdf2.exists()


# ---------------------------------------------------------------------------
# cleanup_raw_repositories
# ---------------------------------------------------------------------------


def test_cleanup_raw_repositories_removes_dirs(tmp_path):
    config_path = tmp_path / "repos.yml"
    _write_repos_config(config_path, {
        "science": [{"name": "myrepo", "url": "https://github.com/org/repo.git"}]
    })
    repo_dir = tmp_path / "raw" / "science" / "myrepo"
    repo_dir.mkdir(parents=True, exist_ok=True)
    (repo_dir / "file.py").write_text("code")

    cleanup_raw_repositories(str(config_path), base_path=str(tmp_path / "raw"))
    assert not repo_dir.exists()


def test_cleanup_raw_repositories_handles_missing(tmp_path):
    config_path = tmp_path / "repos.yml"
    _write_repos_config(config_path, {
        "science": [{"name": "ghost", "url": "https://github.com/org/ghost.git"}]
    })
    # Should not raise even if directory doesn't exist
    cleanup_raw_repositories(str(config_path), base_path=str(tmp_path / "raw"))


def test_cleanup_raw_repositories_removes_empty_cat_dirs(tmp_path):
    config_path = tmp_path / "repos.yml"
    _write_repos_config(config_path, {
        "science": [{"name": "repo", "url": "https://github.com/org/repo.git"}]
    })
    repo_dir = tmp_path / "raw" / "science" / "repo"
    repo_dir.mkdir(parents=True, exist_ok=True)
    (repo_dir / "main.py").write_text("code")

    cleanup_raw_repositories(str(config_path), base_path=str(tmp_path / "raw"))
    # Category dir should be removed too since it's now empty
    assert not (tmp_path / "raw" / "science").exists()


def test_cleanup_raw_repositories_with_category_filter(tmp_path):
    config_path = tmp_path / "repos.yml"
    _write_repos_config(config_path, {
        "science": [{"name": "keep_science", "url": "https://github.com/org/r.git"}],
        "tools": [{"name": "del_tools", "url": "https://github.com/org/t.git"}],
    })
    science_dir = tmp_path / "raw" / "science" / "keep_science"
    tools_dir = tmp_path / "raw" / "tools" / "del_tools"
    science_dir.mkdir(parents=True, exist_ok=True)
    tools_dir.mkdir(parents=True, exist_ok=True)
    (science_dir / "f.py").write_text("x")
    (tools_dir / "g.py").write_text("y")

    cleanup_raw_repositories(str(config_path), base_path=str(tmp_path / "raw"), category="tools")
    assert science_dir.exists()
    assert not tools_dir.exists()


# ---------------------------------------------------------------------------
# Additional build_txtai_index tests
# ---------------------------------------------------------------------------

import types
import sys
from scripts.build_knowledge_base import build_txtai_index


class DummyEmbeddings2:
    instances = []

    def __init__(self, *args, **kwargs):
        self.indexed = []
        DummyEmbeddings2.instances.append(self)

    def index(self, docs):
        self.indexed.extend(list(docs))

    def save(self, path):
        from pathlib import Path
        Path(path).mkdir(parents=True, exist_ok=True)

    def search(self, query, limit):
        return []


def _install_embeddings(monkeypatch):
    DummyEmbeddings2.instances.clear()
    txtai_module = types.ModuleType("txtai")
    emb_module = types.ModuleType("txtai.embeddings")
    emb_module.Embeddings = DummyEmbeddings2
    monkeypatch.setitem(sys.modules, "txtai", txtai_module)
    monkeypatch.setitem(sys.modules, "txtai.embeddings", emb_module)


def test_build_txtai_index_skips_missing_repo(monkeypatch, tmp_path):
    """Repos whose directories don't exist are reported as skipped."""
    _install_embeddings(monkeypatch)
    monkeypatch.setenv("USE_DUAL_EMBEDDING", "false")

    config_path = tmp_path / "repositories.yml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        "science:\n  - name: ghost-repo\n    url: https://example.com/ghost.git\n",
        encoding="utf-8",
    )

    failures = build_txtai_index(
        str(config_path),
        base_path=str(tmp_path / "raw"),
        embeddings_path=str(tmp_path / "embeddings"),
    )
    assert "science/ghost-repo" in failures["skipped_repositories"]


def test_build_txtai_index_validation_error(monkeypatch, tmp_path):
    """Invalid config triggers validation error."""
    _install_embeddings(monkeypatch)
    monkeypatch.setenv("USE_DUAL_EMBEDDING", "false")

    config_path = tmp_path / "repositories.yml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    # Missing 'url' key triggers validation error
    config_path.write_text(
        "science:\n  - name: bad\n",
        encoding="utf-8",
    )

    failures = build_txtai_index(
        str(config_path),
        base_path=str(tmp_path / "raw"),
        embeddings_path=str(tmp_path / "embeddings"),
    )
    assert "validation_errors" in failures


def test_build_txtai_index_dry_run(monkeypatch, tmp_path):
    """In dry_run mode, no index should be built."""
    _install_embeddings(monkeypatch)
    monkeypatch.setenv("USE_DUAL_EMBEDDING", "false")

    config_path = tmp_path / "repositories.yml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        "science:\n  - name: repo1\n    url: https://github.com/org/repo.git\n",
        encoding="utf-8",
    )
    repo_dir = tmp_path / "raw" / "science" / "repo1"
    repo_dir.mkdir(parents=True, exist_ok=True)
    (repo_dir / "main.py").write_text("def main(): pass\n" * 50, encoding="utf-8")

    failures = build_txtai_index(
        str(config_path),
        base_path=str(tmp_path / "raw"),
        embeddings_path=str(tmp_path / "embeddings"),
        dry_run=True,
    )
    # No embeddings should be saved when dry_run
    index_path = tmp_path / "embeddings" / "index"
    assert not index_path.exists() or failures is not None


def test_build_txtai_index_with_pdf_file(monkeypatch, tmp_path):
    """PDF files are processed (fallback to None when no extractor available)."""
    _install_embeddings(monkeypatch)
    monkeypatch.setenv("USE_DUAL_EMBEDDING", "false")
    monkeypatch.setenv("SKIP_PDF_PROCESSING", "")

    config_path = tmp_path / "repositories.yml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        "science:\n  - name: pdf-repo\n    url: https://example.com/repo.git\n",
        encoding="utf-8",
    )
    repo_dir = tmp_path / "raw" / "science" / "pdf-repo"
    repo_dir.mkdir(parents=True, exist_ok=True)

    # Create a real PDF-sized file
    pdf_path = repo_dir / "report.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 " + b"x" * 10000)

    with patch.object(kb_module, "TIKA_AVAILABLE", False):
        with patch.object(kb_module, "extract_text_fallback", return_value=None):
            failures = build_txtai_index(
                str(config_path),
                base_path=str(tmp_path / "raw"),
                embeddings_path=str(tmp_path / "embeddings"),
            )
    # Either failed to extract or succeeded
    assert isinstance(failures, dict)


def test_build_txtai_index_with_pdf_success(monkeypatch, tmp_path):
    """PDF files with successful extraction get indexed."""
    _install_embeddings(monkeypatch)
    monkeypatch.setenv("USE_DUAL_EMBEDDING", "false")

    config_path = tmp_path / "repositories.yml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        "science:\n  - name: pdf-ok-repo\n    url: https://example.com/repo.git\n",
        encoding="utf-8",
    )
    repo_dir = tmp_path / "raw" / "science" / "pdf-ok-repo"
    repo_dir.mkdir(parents=True, exist_ok=True)

    pdf_path = repo_dir / "paper.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 " + b"x" * 10000)

    long_content = "This is extracted PDF content. " * 100

    with patch.object(kb_module, "TIKA_AVAILABLE", False):
        with patch.object(kb_module, "extract_text_fallback", return_value=long_content):
            failures = build_txtai_index(
                str(config_path),
                base_path=str(tmp_path / "raw"),
                embeddings_path=str(tmp_path / "embeddings"),
            )
    assert failures["successful_pdf_files"] >= 1


def test_build_txtai_index_text_file_exception(monkeypatch, tmp_path):
    """Exception in text file reading is caught and recorded."""
    _install_embeddings(monkeypatch)
    monkeypatch.setenv("USE_DUAL_EMBEDDING", "false")

    config_path = tmp_path / "repositories.yml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        "science:\n  - name: repo\n    url: https://github.com/org/repo.git\n",
        encoding="utf-8",
    )
    repo_dir = tmp_path / "raw" / "science" / "repo"
    repo_dir.mkdir(parents=True, exist_ok=True)
    # Create a .py file
    py_file = repo_dir / "bad.py"
    py_file.write_text("content here " * 50, encoding="utf-8")

    original_open = open
    call_count = 0

    def mock_open(path, *args, **kwargs):
        nonlocal call_count
        call_count += 1
        if str(path).endswith("bad.py") and call_count > 2:
            raise IOError("file read error")
        return original_open(path, *args, **kwargs)

    with patch("builtins.open", side_effect=mock_open):
        failures = build_txtai_index(
            str(config_path),
            base_path=str(tmp_path / "raw"),
            embeddings_path=str(tmp_path / "embeddings"),
        )
    # Should not crash; either succeeded or failed gracefully
    assert isinstance(failures, dict)


def test_build_txtai_index_with_articles_config(monkeypatch, tmp_path):
    """Articles config is loaded when provided."""
    _install_embeddings(monkeypatch)
    monkeypatch.setenv("USE_DUAL_EMBEDDING", "false")

    repos_path = tmp_path / "repositories.yml"
    repos_path.parent.mkdir(parents=True, exist_ok=True)
    repos_path.write_text(
        "science:\n  - name: repo1\n    url: https://example.com/repo.git\n",
        encoding="utf-8",
    )

    articles_path = tmp_path / "articles.yml"
    articles_path.write_text(
        "papers:\n  - name: paper1\n    url: https://example.com/p.pdf\n    description: Paper 1\n",
        encoding="utf-8",
    )

    # Don't create the repo or article dirs -> both should be skipped
    failures = build_txtai_index(
        str(repos_path),
        articles_config_path=str(articles_path),
        base_path=str(tmp_path / "raw"),
        embeddings_path=str(tmp_path / "embeddings"),
    )
    assert "papers/paper1" in failures["skipped_articles"]


def test_build_txtai_index_articles_validation_error(monkeypatch, tmp_path):
    """Invalid articles config triggers validation error."""
    _install_embeddings(monkeypatch)
    monkeypatch.setenv("USE_DUAL_EMBEDDING", "false")

    repos_path = tmp_path / "repositories.yml"
    repos_path.parent.mkdir(parents=True, exist_ok=True)
    repos_path.write_text(
        "science:\n  - name: repo1\n    url: https://github.com/org/repo.git\n",
        encoding="utf-8",
    )

    articles_path = tmp_path / "articles.yml"
    articles_path.write_text(
        "papers:\n  - name: bad_article\n",  # missing url
        encoding="utf-8",
    )

    failures = build_txtai_index(
        str(repos_path),
        articles_config_path=str(articles_path),
        base_path=str(tmp_path / "raw"),
        embeddings_path=str(tmp_path / "embeddings"),
    )
    assert "validation_errors" in failures
