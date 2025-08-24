"""
Tests for admin UI utility functions.
"""

import tempfile
import yaml
from pathlib import Path


def test_load_config():
    """Test loading repository configuration."""
    # Import here to avoid streamlit import during test collection
    from nancy_brain.admin_ui import load_config

    with tempfile.TemporaryDirectory() as tmpdir:
        config_file = Path(tmpdir) / "config" / "repositories.yml"
        config_file.parent.mkdir()
        config_file.write_text(
            """
test_tools:
  - name: test-repo
    url: https://github.com/test/repo.git
"""
        )

        # Change to tmpdir for test
        import os

        old_cwd = os.getcwd()
        try:
            os.chdir(tmpdir)
            config = load_config()
            assert config is not None
            assert "test_tools" in config
            assert len(config["test_tools"]) == 1
            assert config["test_tools"][0]["name"] == "test-repo"
        finally:
            os.chdir(old_cwd)


def test_load_config_missing():
    """Test loading config when file doesn't exist."""
    from nancy_brain.admin_ui import load_config

    with tempfile.TemporaryDirectory() as tmpdir:
        import os

        old_cwd = os.getcwd()
        try:
            os.chdir(tmpdir)
            config = load_config()
            assert config == {}
        finally:
            os.chdir(old_cwd)


def test_load_articles_config():
    """Test loading articles configuration."""
    from nancy_brain.admin_ui import load_articles_config

    with tempfile.TemporaryDirectory() as tmpdir:
        config_file = Path(tmpdir) / "config" / "articles.yml"
        config_file.parent.mkdir()
        config_file.write_text(
            """
papers:
  - name: test-paper
    url: https://arxiv.org/pdf/test.pdf
    description: A test paper
"""
        )

        import os

        old_cwd = os.getcwd()
        try:
            os.chdir(tmpdir)
            config = load_articles_config()
            assert config is not None
            assert "papers" in config
            assert len(config["papers"]) == 1
            assert config["papers"][0]["name"] == "test-paper"
        finally:
            os.chdir(old_cwd)


def test_save_articles_config():
    """Test saving articles configuration."""
    from nancy_brain.admin_ui import save_articles_config

    with tempfile.TemporaryDirectory() as tmpdir:
        config_file = Path(tmpdir) / "config" / "articles.yml"

        config = {
            "papers": [
                {
                    "name": "test-paper",
                    "url": "https://arxiv.org/pdf/test.pdf",
                    "description": "A test paper",
                }
            ]
        }

        save_articles_config(config, config_file)

        assert config_file.exists()
        with open(config_file) as f:
            saved_config = yaml.safe_load(f)

        assert saved_config == config


def test_run_build_command():
    """Test the build command execution."""
    from nancy_brain.admin_ui import run_build_command

    # Just test that the function exists and doesn't crash when called
    # We'll mock subprocess to avoid actual execution
    try:
        from unittest.mock import patch

        with patch("nancy_brain.admin_ui.subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            mock_run.return_value.stdout = "Build completed"
            mock_run.return_value.stderr = ""

            # Test basic build command
            result = run_build_command()

            # Should return the subprocess result
            assert result is not None
            mock_run.assert_called_once()

    except ImportError:
        # If mock not available, just test function exists
        assert callable(run_build_command)
