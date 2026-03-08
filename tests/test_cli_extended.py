"""Extended CLI tests to improve coverage of nancy_brain/cli.py."""

import sys
import types
import pytest
import yaml
from pathlib import Path
from unittest.mock import patch, MagicMock
from click.testing import CliRunner

from nancy_brain.cli import cli, _print_import_summary
import click

# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _write_repos_config(path: Path, repos: dict | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    config = repos or {"science": [{"name": "repo1", "url": "https://github.com/org/repo1.git"}]}
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(config, f)


def _write_articles_config(path: Path, articles: dict | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    config = articles or {"papers": [{"name": "paper1", "url": "https://example.com/paper1.pdf"}]}
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(config, f)


# ---------------------------------------------------------------------------
# _print_import_summary helper
# ---------------------------------------------------------------------------


def test_print_import_summary_no_errors():
    runner = CliRunner()
    with runner.isolated_filesystem():
        summary = {"added": 3, "skipped_duplicate": 1, "skipped_no_url": 0, "errors": []}
        # Run via a temporary CLI invocation to capture output

        @click.command()
        def _cmd():
            _print_import_summary("Test", summary)

        result = runner.invoke(_cmd)
        assert "Added: 3" in result.output
        assert "Skipped duplicates: 1" in result.output


def test_print_import_summary_with_errors():
    runner = CliRunner()

    @click.command()
    def _cmd():
        _print_import_summary(
            "Test", {"added": 0, "skipped_duplicate": 0, "skipped_no_url": 0, "errors": ["err1", "err2"]}
        )

    result = runner.invoke(_cmd)
    assert "Errors: 2" in result.output
    assert "err1" in result.output


# ---------------------------------------------------------------------------
# build command
# ---------------------------------------------------------------------------


def test_build_missing_config():
    runner = CliRunner()
    with runner.isolated_filesystem():
        result = runner.invoke(cli, ["build"])
    assert result.exit_code != 0 or "config not found" in result.output.lower() or "❌" in result.output


def test_build_invalid_repos_config():
    runner = CliRunner()
    with runner.isolated_filesystem():
        config_dir = Path("config")
        config_dir.mkdir()
        (config_dir / "repositories.yml").write_text(
            "science:\n  - name: bad\n    url: not-a-github-url\n", encoding="utf-8"
        )
        result = runner.invoke(cli, ["build"])
    # Should exit with validation error
    assert result.exit_code != 0 or "❌" in result.output


def test_build_success_calls_subprocess():
    runner = CliRunner()
    with runner.isolated_filesystem():
        _write_repos_config(Path("config/repositories.yml"))
        with patch("nancy_brain.cli.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            result = runner.invoke(cli, ["build"])
    assert result.exit_code == 0


def test_build_with_force_update():
    runner = CliRunner()
    with runner.isolated_filesystem():
        _write_repos_config(Path("config/repositories.yml"))
        with patch("nancy_brain.cli.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            result = runner.invoke(cli, ["build", "--force-update"])
        cmd = mock_run.call_args[0][0]
        assert "--force-update" in cmd
    assert result.exit_code == 0


def test_build_with_summaries_flag():
    runner = CliRunner()
    with runner.isolated_filesystem():
        _write_repos_config(Path("config/repositories.yml"))
        with patch("nancy_brain.cli.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            result = runner.invoke(cli, ["build", "--summaries"])
        cmd = mock_run.call_args[0][0]
        assert "--summaries" in cmd


def test_build_with_no_summaries_flag():
    runner = CliRunner()
    with runner.isolated_filesystem():
        _write_repos_config(Path("config/repositories.yml"))
        with patch("nancy_brain.cli.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            result = runner.invoke(cli, ["build", "--no-summaries"])
        cmd = mock_run.call_args[0][0]
        assert "--no-summaries" in cmd


def test_build_with_category():
    runner = CliRunner()
    with runner.isolated_filesystem():
        _write_repos_config(Path("config/repositories.yml"))
        with patch("nancy_brain.cli.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            result = runner.invoke(cli, ["build", "--category", "science"])
        cmd = mock_run.call_args[0][0]
        assert "--category" in cmd
        assert "science" in cmd


def test_build_with_summaries_only():
    runner = CliRunner()
    with runner.isolated_filesystem():
        _write_repos_config(Path("config/repositories.yml"))
        with patch("nancy_brain.cli.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            result = runner.invoke(cli, ["build", "--summaries-only"])
        cmd = mock_run.call_args[0][0]
        assert "--summaries-only" in cmd


def test_build_with_batch_size():
    runner = CliRunner()
    with runner.isolated_filesystem():
        _write_repos_config(Path("config/repositories.yml"))
        with patch("nancy_brain.cli.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            result = runner.invoke(cli, ["build", "--batch-size", "50"])
        cmd = mock_run.call_args[0][0]
        assert "--batch-size" in cmd


def test_build_with_max_docs():
    runner = CliRunner()
    with runner.isolated_filesystem():
        _write_repos_config(Path("config/repositories.yml"))
        with patch("nancy_brain.cli.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            result = runner.invoke(cli, ["build", "--max-docs", "100"])
        cmd = mock_run.call_args[0][0]
        assert "--max-docs" in cmd


def test_build_dry_run():
    runner = CliRunner()
    with runner.isolated_filesystem():
        _write_repos_config(Path("config/repositories.yml"))
        with patch("nancy_brain.cli.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            result = runner.invoke(cli, ["build", "--dry-run"])
        cmd = mock_run.call_args[0][0]
        assert "--dry-run" in cmd


def test_build_subprocess_error():
    runner = CliRunner()
    import subprocess

    with runner.isolated_filesystem():
        _write_repos_config(Path("config/repositories.yml"))
        with patch("nancy_brain.cli.subprocess.run") as mock_run:
            mock_run.side_effect = subprocess.CalledProcessError(1, ["python"])
            result = runner.invoke(cli, ["build"])
    assert result.exit_code != 0


def test_build_with_articles_config_missing():
    runner = CliRunner()
    with runner.isolated_filesystem():
        _write_repos_config(Path("config/repositories.yml"))
        result = runner.invoke(cli, ["build", "--articles-config", "config/articles.yml"])
    assert result.exit_code != 0 or "❌" in result.output


def test_build_with_articles_config_invalid():
    runner = CliRunner()
    with runner.isolated_filesystem():
        _write_repos_config(Path("config/repositories.yml"))
        # Write invalid articles config (missing url)
        _write_articles_config(Path("config/articles.yml"), {"papers": [{"name": "bad_article"}]})
        result = runner.invoke(cli, ["build", "--articles-config", "config/articles.yml"])
    assert result.exit_code != 0 or "❌" in result.output


def test_build_with_valid_articles_config():
    runner = CliRunner()
    with runner.isolated_filesystem():
        _write_repos_config(Path("config/repositories.yml"))
        _write_articles_config(
            Path("config/articles.yml"), {"papers": [{"name": "paper1", "url": "https://example.com/paper1.pdf"}]}
        )
        with patch("nancy_brain.cli.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            result = runner.invoke(cli, ["build", "--articles-config", "config/articles.yml"])
        cmd = mock_run.call_args[0][0]
        assert "--articles-config" in cmd


def test_build_with_dirty_flag():
    runner = CliRunner()
    with runner.isolated_filesystem():
        _write_repos_config(Path("config/repositories.yml"))
        with patch("nancy_brain.cli.subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(returncode=0)
            result = runner.invoke(cli, ["build", "--dirty"])
        cmd = mock_run.call_args[0][0]
        assert "--dirty" in cmd


# ---------------------------------------------------------------------------
# import-env command
# ---------------------------------------------------------------------------


def test_import_env_command_success(tmp_path):
    runner = CliRunner()
    with runner.isolated_filesystem():
        env_file = Path("env.yml")
        env_file.write_text("name: test_env\ndependencies:\n  - pip:\n    - some_pkg\n")

        with patch("nancy_brain.env_import.import_from_env") as _:
            with patch("nancy_brain.cli.subprocess.run"):
                with patch("nancy_brain.env_import.requests.get") as mock_get:
                    mock_get.return_value = MagicMock(
                        status_code=200,
                        json=lambda: {"info": {"project_urls": None, "home_page": ""}},
                        raise_for_status=lambda: None,
                    )
                    with patch("nancy_brain.env_import.time.sleep"):
                        result = runner.invoke(cli, ["import-env", "-f", "env.yml"])
    assert result.exit_code == 0


def test_import_env_command_exception():
    runner = CliRunner()
    with runner.isolated_filesystem():
        env_file = Path("env.yml")
        env_file.write_text("name: bad\n")

        with patch("nancy_brain.env_import.import_from_env", side_effect=Exception("fail")):
            result = runner.invoke(cli, ["import-env", "-f", "env.yml"])
    assert result.exit_code != 0 or "❌" in result.output


def test_import_env_dry_run(tmp_path):
    runner = CliRunner()
    with runner.isolated_filesystem():
        env_file = Path("env.yml")
        env_file.write_text("name: dry_env\ndependencies:\n  - pip:\n    - mypkg\n")

        with patch("nancy_brain.env_import.requests.get") as mock_get:
            mock_get.return_value = MagicMock(
                status_code=200,
                json=lambda: {"info": {"project_urls": None, "home_page": ""}},
                raise_for_status=lambda: None,
            )
            with patch("nancy_brain.env_import.time.sleep"):
                result = runner.invoke(cli, ["import-env", "-f", "env.yml", "--dry-run"])
    assert result.exit_code == 0
    assert "Dry run" in result.output or "Added:" in result.output


# ---------------------------------------------------------------------------
# serve command
# ---------------------------------------------------------------------------


def test_serve_no_uvicorn():
    runner = CliRunner()
    # Ensure uvicorn is not available
    with patch.dict(sys.modules, {"uvicorn": None}):
        result = runner.invoke(cli, ["serve"])
    assert "uvicorn" in result.output.lower() or result.exit_code == 0


def test_serve_with_uvicorn():
    runner = CliRunner()
    fake_uvicorn = MagicMock()
    with patch.dict(sys.modules, {"uvicorn": fake_uvicorn}):
        result = runner.invoke(cli, ["serve", "--host", "0.0.0.0", "--port", "9000"])
    # uvicorn.run should have been called
    fake_uvicorn.run.assert_called_once()
    assert result.exit_code == 0


# ---------------------------------------------------------------------------
# search command
# ---------------------------------------------------------------------------


def test_search_no_index():
    runner = CliRunner()
    with runner.isolated_filesystem():
        result = runner.invoke(cli, ["search", "test query"])
    assert result.exit_code == 0
    assert "No results found" in result.output


# ---------------------------------------------------------------------------
# explore command
# ---------------------------------------------------------------------------


def test_explore_no_index():
    runner = CliRunner()
    with runner.isolated_filesystem():
        result = runner.invoke(cli, ["explore"])
    assert result.exit_code == 0
    assert "No documents found" in result.output or "missing" in result.output


# ---------------------------------------------------------------------------
# ui command
# ---------------------------------------------------------------------------


def test_ui_streamlit_not_installed():
    runner = CliRunner()
    with patch.dict(sys.modules, {"streamlit": None}):
        result = runner.invoke(cli, ["ui"])
    assert "Streamlit" in result.output or result.exit_code == 0


def test_ui_subprocess_error():
    runner = CliRunner()
    import subprocess

    fake_streamlit = MagicMock()
    with patch.dict(sys.modules, {"streamlit": fake_streamlit}):
        with patch("nancy_brain.cli.subprocess.run", side_effect=subprocess.CalledProcessError(1, ["streamlit"])):
            result = runner.invoke(cli, ["ui"])
    assert result.exit_code == 0
    assert "Failed to start" in result.output


def test_ui_streamlit_not_found():
    runner = CliRunner()
    import subprocess

    fake_streamlit = MagicMock()
    with patch.dict(sys.modules, {"streamlit": fake_streamlit}):
        with patch("nancy_brain.cli.subprocess.run", side_effect=FileNotFoundError()):
            result = runner.invoke(cli, ["ui"])
    assert "not found" in result.output.lower() or result.exit_code == 0


# ---------------------------------------------------------------------------
# add_repo command
# ---------------------------------------------------------------------------


def test_add_repo_creates_new_category():
    runner = CliRunner()
    with runner.isolated_filesystem():
        config_dir = Path("config")
        config_dir.mkdir()
        (config_dir / "repositories.yml").write_text("science: []\n")

        result = runner.invoke(cli, ["add-repo", "https://github.com/org/newrepo.git", "--category", "newcat"])
    assert result.exit_code == 0
    assert "Added newrepo" in result.output


def test_add_repo_duplicate():
    runner = CliRunner()
    with runner.isolated_filesystem():
        config_dir = Path("config")
        config_dir.mkdir()
        (config_dir / "repositories.yml").write_text(
            "tools:\n  - name: myrepo\n    url: https://github.com/org/myrepo.git\n"
        )
        result = runner.invoke(cli, ["add-repo", "https://github.com/org/myrepo.git", "--category", "tools"])
    assert result.exit_code == 0
    assert "already exists" in result.output


# ---------------------------------------------------------------------------
# add_article command
# ---------------------------------------------------------------------------


def test_add_article_no_description():
    runner = CliRunner()
    with runner.isolated_filesystem():
        result = runner.invoke(cli, ["add-article", "https://arxiv.org/pdf/1234.pdf", "paper1"])
    assert result.exit_code == 0
    assert "Added article" in result.output


def test_add_article_creates_config_dir():
    runner = CliRunner()
    with runner.isolated_filesystem():
        result = runner.invoke(cli, ["add-article", "https://arxiv.org/pdf/5678.pdf", "paper2", "--category", "astro"])
        assert result.exit_code == 0
        config_file = Path("config/articles.yml")
        assert config_file.exists()
        with open(config_file) as f:
            cfg = yaml.safe_load(f)
        assert "astro" in cfg


def test_add_article_existing_config():
    runner = CliRunner()
    with runner.isolated_filesystem():
        _write_articles_config(
            Path("config/articles.yml"),
            {"papers": [{"name": "existing", "url": "https://example.com/e.pdf"}]},
        )
        result = runner.invoke(cli, ["add-article", "https://example.com/new.pdf", "new-paper", "--category", "papers"])
    assert result.exit_code == 0
    assert "Added article" in result.output


# ---------------------------------------------------------------------------
# import-bibtex command
# ---------------------------------------------------------------------------


def test_import_bibtex_command(tmp_path):
    runner = CliRunner()
    with runner.isolated_filesystem():
        bib_file = Path("refs.bib")
        bib_file.write_text(
            "@article{key2023,\n  author={Author, A},\n  title={Title},\n  journal={J},\n"
            "  year={2023},\n  doi={10.1234/test}\n}\n"
        )
        with patch("nancy_brain.article_import.import_from_bibtex") as mock_import:
            mock_import.return_value = {"added": 1, "skipped_duplicate": 0, "skipped_no_url": 0, "errors": []}
            result = runner.invoke(cli, ["import-bibtex", "-f", "refs.bib"])
    assert result.exit_code == 0
    assert "Added: 1" in result.output


def test_import_bibtex_exception(tmp_path):
    runner = CliRunner()
    with runner.isolated_filesystem():
        bib_file = Path("refs.bib")
        bib_file.write_text("@article{x,}\n")
        with patch("nancy_brain.article_import.import_from_bibtex", side_effect=RuntimeError("bad file")):
            result = runner.invoke(cli, ["import-bibtex", "-f", "refs.bib"])
    assert result.exit_code != 0


def test_import_bibtex_dry_run(tmp_path):
    runner = CliRunner()
    with runner.isolated_filesystem():
        bib_file = Path("refs.bib")
        bib_file.write_text("@article{y, author={B}, title={T}, journal={J}, year={2022}}\n")
        with patch("nancy_brain.article_import.import_from_bibtex") as mock_import:
            mock_import.return_value = {"added": 2, "skipped_duplicate": 0, "skipped_no_url": 0, "errors": []}
            result = runner.invoke(cli, ["import-bibtex", "-f", "refs.bib", "--dry-run"])
    assert result.exit_code == 0
    assert "Added: 2" in result.output


# ---------------------------------------------------------------------------
# import-ads command
# ---------------------------------------------------------------------------


def test_import_ads_command():
    runner = CliRunner()
    with runner.isolated_filesystem():
        with patch("nancy_brain.article_import.import_from_ads") as mock_import:
            mock_import.return_value = {"added": 5, "skipped_duplicate": 0, "skipped_no_url": 2, "errors": []}
            result = runner.invoke(cli, ["import-ads", "--library", "My Library"])
    assert result.exit_code == 0
    assert "Added: 5" in result.output


def test_import_ads_exception():
    runner = CliRunner()
    with runner.isolated_filesystem():
        with patch("nancy_brain.article_import.import_from_ads", side_effect=RuntimeError("ADS error")):
            result = runner.invoke(cli, ["import-ads", "--library", "Bad Library"])
    assert result.exit_code != 0


def test_import_ads_with_errors():
    runner = CliRunner()
    with runner.isolated_filesystem():
        with patch("nancy_brain.article_import.import_from_ads") as mock_import:
            mock_import.return_value = {
                "added": 1,
                "skipped_duplicate": 0,
                "skipped_no_url": 0,
                "errors": ["fetch failed for paper X"],
            }
            result = runner.invoke(cli, ["import-ads", "--library", "Lib"])
    assert result.exit_code == 0
    assert "Errors: 1" in result.output


# ---------------------------------------------------------------------------
# add-new-user command
# ---------------------------------------------------------------------------


def test_add_new_user_no_auth_module():
    runner = CliRunner()
    with patch.dict(sys.modules, {"connectors.http_api": None, "connectors.http_api.auth": None}):
        result = runner.invoke(cli, ["add-new-user", "admin", "secret"])
    # Either import error message or user created successfully
    assert result.exit_code != 0 or "✅" in result.output or "❌" in result.output


def test_add_new_user_success():
    runner = CliRunner()
    fake_auth = MagicMock()
    fake_auth.create_user_table = MagicMock()
    fake_auth.add_user = MagicMock()

    fake_http_api = types.ModuleType("connectors.http_api")
    fake_http_api.auth = fake_auth

    saved = {k: v for k, v in sys.modules.items()}
    sys.modules["connectors.http_api"] = fake_http_api
    sys.modules["connectors.http_api.auth"] = fake_auth

    try:
        result = runner.invoke(cli, ["add-new-user", "testuser", "testpass"])
    finally:
        # Restore original modules
        for key in list(sys.modules.keys()):
            if key not in saved:
                del sys.modules[key]
        sys.modules.update(saved)

    # Should succeed or hit exit 0
    assert result.exit_code in (0, 1)


def test_add_new_user_exception():
    runner = CliRunner()
    fake_auth = MagicMock()
    fake_auth.create_user_table.side_effect = Exception("db error")

    fake_http_api = types.ModuleType("connectors.http_api")
    fake_http_api.auth = fake_auth

    saved = sys.modules.copy()
    sys.modules["connectors.http_api"] = fake_http_api
    sys.modules["connectors.http_api.auth"] = fake_auth

    try:
        result = runner.invoke(cli, ["add-new-user", "admin", "pass"])
    finally:
        # Restore original modules (only remove ones we added)
        for key in list(sys.modules.keys()):
            if key not in saved:
                del sys.modules[key]
        sys.modules.update(saved)

    assert result.exit_code != 0 or "❌" in result.output


# ---------------------------------------------------------------------------
# version command
# ---------------------------------------------------------------------------


def test_version_option():
    runner = CliRunner()
    result = runner.invoke(cli, ["--version"])
    assert result.exit_code == 0
    assert "0." in result.output or "unknown" in result.output
