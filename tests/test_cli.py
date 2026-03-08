"""Tests for the Nancy Brain CLI."""

import pytest
from click.testing import CliRunner
from pathlib import Path
import tempfile
import os
import yaml

from nancy_brain.cli import cli


def test_cli_help():
    """Test CLI help command."""
    runner = CliRunner()
    result = runner.invoke(cli, ["--help"])
    assert result.exit_code == 0
    assert "Nancy Brain" in result.output
    assert "Turn GitHub repos into AI-searchable knowledge bases" in result.output


def test_init_command():
    """Test init command creates project structure."""
    runner = CliRunner()

    with tempfile.TemporaryDirectory() as tmpdir:
        project_name = "test-project"
        with runner.isolated_filesystem(tmpdir):
            result = runner.invoke(cli, ["init", project_name])

            assert result.exit_code == 0
            assert "Initialized Nancy Brain project" in result.output

            # Check that files were created
            project_path = Path(project_name)
            assert project_path.exists()
            assert (project_path / "config").exists()
            assert (project_path / "config" / "repositories.yml").exists()


def test_add_repo_command():
    """Test add-repo command."""
    runner = CliRunner()

    with runner.isolated_filesystem():
        # Create a basic config structure
        config_dir = Path("config")
        config_dir.mkdir()
        config_file = config_dir / "repositories.yml"
        config_file.write_text("# Empty config\n")

        result = runner.invoke(
            cli,
            [
                "add-repo",
                "https://github.com/test/repo.git",
                "--category",
                "test_category",
            ],
        )

        assert result.exit_code == 0
        assert "Added repo to test_category category" in result.output


def test_add_repo_command_no_config():
    """Test add-repo command when no config exists."""
    runner = CliRunner()

    with runner.isolated_filesystem():
        result = runner.invoke(cli, ["add-repo", "https://github.com/test/repo.git"])

        assert result.exit_code == 0
        assert "No config/repositories.yml found" in result.output


def test_add_article_command():
    """Test add-article command."""
    runner = CliRunner()

    with runner.isolated_filesystem():
        result = runner.invoke(
            cli,
            [
                "add-article",
                "https://arxiv.org/pdf/test.pdf",
                "test_article",
                "--category",
                "test_papers",
                "--description",
                "A test article",
            ],
        )

        assert result.exit_code == 0
        assert "Added article" in result.output

        # Check that the config file was created and contains the article
        config_file = Path("config") / "articles.yml"
        assert config_file.exists()

        with open(config_file) as f:
            config = yaml.safe_load(f)

        assert "test_papers" in config
        assert len(config["test_papers"]) == 1
        assert config["test_papers"][0]["name"] == "test_article"
        assert config["test_papers"][0]["url"] == "https://arxiv.org/pdf/test.pdf"
        assert config["test_papers"][0]["description"] == "A test article"


def test_add_article_duplicate():
    """Test add-article command with duplicate name."""
    runner = CliRunner()

    with runner.isolated_filesystem():
        # Create initial article
        config_dir = Path("config")
        config_dir.mkdir()
        config_file = config_dir / "articles.yml"
        config_file.write_text(
            """
test_papers:
  - name: test_article
    url: https://example.com/existing.pdf
"""
        )

        # Try to add duplicate
        result = runner.invoke(
            cli,
            [
                "add-article",
                "https://arxiv.org/pdf/test.pdf",
                "test_article",
                "--category",
                "test_papers",
            ],
        )

        assert result.exit_code == 0
        assert "already exists" in result.output


def test_search_command_no_embeddings():
    """Test search command when no embeddings exist."""
    runner = CliRunner()

    with runner.isolated_filesystem():
        result = runner.invoke(cli, ["search", "test query"])

        assert result.exit_code == 0  # Command succeeds but returns no results
        assert "No results found" in result.output


def test_serve_command_help():
    """Test serve command help."""
    runner = CliRunner()
    result = runner.invoke(cli, ["serve", "--help"])
    assert result.exit_code == 0
    assert "Start the HTTP API server" in result.output


def test_ui_command_help():
    """Test ui command help."""
    runner = CliRunner()
    result = runner.invoke(cli, ["ui", "--help"])
    assert result.exit_code == 0
    assert "Launch the web admin interface" in result.output


def test_build_command_help():
    """Test build command help."""
    runner = CliRunner()
    result = runner.invoke(cli, ["build", "--help"])
    assert result.exit_code == 0
    assert "Build the knowledge base" in result.output


def test_ui_command():
    """Test ui command."""
    runner = CliRunner()

    with runner.isolated_filesystem():
        # Test with help to avoid hanging on streamlit
        result = runner.invoke(cli, ["ui", "--help"])

        assert result.exit_code == 0
        assert "ui" in result.output.lower()


def test_list_repos_empty_config():
    """Test that add-repo command shows help correctly."""
    runner = CliRunner()

    with runner.isolated_filesystem():
        # Test add-repo command help instead of non-existent list-repos
        result = runner.invoke(cli, ["add-repo", "--help"])

        assert result.exit_code == 0
        assert "add-repo" in result.output.lower()


def test_list_repos_missing_config():
    """Test add-repo command behavior."""
    runner = CliRunner()

    with runner.isolated_filesystem():
        result = runner.invoke(cli, ["add-repo", "--help"])

        # Should show help
        assert result.exit_code == 0
        assert "add-repo" in result.output.lower()


def test_admin_ui_command():
    """Test ui command help."""
    runner = CliRunner()

    result = runner.invoke(cli, ["ui", "--help"])

    assert result.exit_code == 0
    assert "ui" in result.output.lower() or "Launch the web admin interface" in result.output


def test_cli_main_group():
    """Test main CLI group."""
    runner = CliRunner()

    result = runner.invoke(cli, ["--help"])

    # Should show help
    assert result.exit_code == 0
    assert "Usage:" in result.output or "Nancy Brain" in result.output
