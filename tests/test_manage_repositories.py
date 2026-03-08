"""Tests for scripts/manage_repositories.py - RepositoryManager class."""

import pytest
import yaml
from pathlib import Path
from unittest.mock import patch, MagicMock, call
import subprocess

from scripts.manage_repositories import RepositoryManager


def _write_config(path: Path, config: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(config, f)


@pytest.fixture
def manager(tmp_path):
    return RepositoryManager(base_path=str(tmp_path / "repos"))


@pytest.fixture
def simple_config():
    return {
        "science": [
            {"name": "repo-a", "url": "https://github.com/org/repo-a.git", "description": "Repo A"},
            {"name": "repo-b", "url": "https://github.com/org/repo-b.git", "description": "Repo B"},
        ]
    }


# ---------------------------------------------------------------------------
# RepositoryManager.__init__
# ---------------------------------------------------------------------------


def test_init_creates_base_path(tmp_path):
    base = tmp_path / "deep" / "nested" / "repos"
    manager = RepositoryManager(base_path=str(base))
    assert base.exists()


# ---------------------------------------------------------------------------
# load_config / save_config
# ---------------------------------------------------------------------------


def test_load_config_existing(tmp_path, manager, simple_config):
    config_file = tmp_path / "repos.yml"
    _write_config(config_file, simple_config)
    loaded = manager.load_config(str(config_file))
    assert loaded == simple_config


def test_load_config_missing_returns_none(tmp_path, manager):
    result = manager.load_config(str(tmp_path / "nonexistent.yml"))
    assert result is None


def test_save_config_roundtrip(tmp_path, manager, simple_config):
    config_file = tmp_path / "out.yml"
    manager.save_config(simple_config, str(config_file))
    assert config_file.exists()
    with open(config_file, "r") as f:
        loaded = yaml.safe_load(f)
    assert loaded["science"][0]["name"] == "repo-a"


# ---------------------------------------------------------------------------
# run_command
# ---------------------------------------------------------------------------


def test_run_command_success(manager):
    with patch("scripts.manage_repositories.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        result = manager.run_command(["git", "clone", "https://example.com/x.git", "/tmp/x"])
    assert result is True


def test_run_command_failure(manager):
    with patch("scripts.manage_repositories.subprocess.run") as mock_run:
        mock_run.side_effect = subprocess.CalledProcessError(1, ["git"], stderr="fatal: not a repo")
        result = manager.run_command(["git", "pull"])
    assert result is False


# ---------------------------------------------------------------------------
# clone_repository
# ---------------------------------------------------------------------------


def test_clone_new_repo_no_ref(tmp_path, manager):
    repo_info = {"name": "my-repo", "url": "https://github.com/org/my-repo.git"}
    with patch.object(manager, "run_command", return_value=True) as mock_cmd:
        result = manager.clone_repository(repo_info, "science")
    assert result is True
    clone_call = mock_cmd.call_args_list[0][0][0]
    assert clone_call[:2] == ["git", "clone"]
    assert "--depth" in clone_call


def test_clone_new_repo_with_tag_ref(tmp_path, manager):
    repo_info = {"name": "tagged-repo", "url": "https://github.com/org/repo.git", "ref": "v1.0.0"}
    with patch.object(manager, "run_command", return_value=True) as mock_cmd:
        result = manager.clone_repository(repo_info, "science")
    assert result is True
    clone_call = mock_cmd.call_args_list[0][0][0]
    assert "--branch" in clone_call
    assert "v1.0.0" in clone_call


def test_clone_new_repo_with_full_sha_ref(tmp_path, manager):
    sha = "a" * 40
    repo_info = {"name": "sha-repo", "url": "https://github.com/org/repo.git", "ref": sha}
    with patch.object(manager, "run_command", return_value=True) as mock_cmd:
        result = manager.clone_repository(repo_info, "science")
    assert result is True
    # First call: clone without --branch
    clone_call = mock_cmd.call_args_list[0][0][0]
    assert "--branch" not in clone_call
    assert clone_call[:2] == ["git", "clone"]
    # Second call: checkout the SHA
    checkout_call = mock_cmd.call_args_list[1][0][0]
    assert checkout_call == ["git", "checkout", sha]


def test_clone_new_repo_sha_checkout_fails(tmp_path, manager):
    sha = "b" * 40
    repo_info = {"name": "sha-repo2", "url": "https://github.com/org/repo.git", "ref": sha}
    with patch.object(manager, "run_command", side_effect=[True, False]):
        result = manager.clone_repository(repo_info, "science")
    assert result is False


def test_clone_existing_repo_calls_update(tmp_path, manager):
    repo_info = {"name": "existing-repo", "url": "https://github.com/org/repo.git"}
    repo_path = manager.base_path / "science" / "existing-repo"
    repo_path.mkdir(parents=True, exist_ok=True)

    with patch.object(manager, "update_repository", return_value=True) as mock_update:
        result = manager.clone_repository(repo_info, "science")
    assert result is True
    mock_update.assert_called_once()


def test_clone_new_repo_fails_returns_false(tmp_path, manager):
    repo_info = {"name": "bad-repo", "url": "https://github.com/org/bad.git"}
    with patch.object(manager, "run_command", return_value=False):
        result = manager.clone_repository(repo_info, "science")
    assert result is False


# ---------------------------------------------------------------------------
# update_repository
# ---------------------------------------------------------------------------


def test_update_repo_no_ref(tmp_path, manager):
    repo_path = tmp_path / "repos" / "science" / "myrepo"
    repo_path.mkdir(parents=True, exist_ok=True)

    with patch("scripts.manage_repositories.subprocess.run") as mock_run:
        # fetch returns success; rev-parse returns branch name
        mock_run.return_value = MagicMock(returncode=0, stdout="main\n")
        with patch.object(manager, "run_command", side_effect=[True, True]):
            result = manager.update_repository(repo_path)
    assert result is True


def test_update_repo_with_tag_ref(tmp_path, manager):
    repo_path = tmp_path / "repos" / "science" / "repo"
    repo_path.mkdir(parents=True, exist_ok=True)

    with patch.object(manager, "run_command", return_value=True):
        result = manager.update_repository(repo_path, repo_config={"ref": "v2.0.0"})
    assert result is True


def test_update_repo_with_full_sha_ref(tmp_path, manager):
    sha = "c" * 40
    repo_path = tmp_path / "repos" / "science" / "repo"
    repo_path.mkdir(parents=True, exist_ok=True)

    with patch.object(manager, "run_command", return_value=True):
        result = manager.update_repository(repo_path, repo_config={"ref": sha})
    assert result is True


def test_update_repo_fetch_fails(tmp_path, manager):
    repo_path = tmp_path / "repos" / "science" / "repo"
    repo_path.mkdir(parents=True, exist_ok=True)

    with patch.object(manager, "run_command", return_value=False):
        result = manager.update_repository(repo_path, repo_config={"ref": "v1.0"})
    assert result is False


def test_update_repo_pull_fails(tmp_path, manager):
    repo_path = tmp_path / "repos" / "science" / "repo"
    repo_path.mkdir(parents=True, exist_ok=True)

    with patch("scripts.manage_repositories.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="main\n")
        with patch.object(manager, "run_command", side_effect=[True, False]):
            result = manager.update_repository(repo_path)
    assert result is False


# ---------------------------------------------------------------------------
# process_category / process_all
# ---------------------------------------------------------------------------


def test_process_category_counts_successes(tmp_path, manager, simple_config):
    repos = simple_config["science"]
    with patch.object(manager, "clone_repository", side_effect=[True, False]):
        count = manager.process_category("science", repos)
    assert count == 1


def test_process_all_returns_dict(tmp_path, manager, simple_config):
    with patch.object(manager, "clone_repository", return_value=True):
        results = manager.process_all(simple_config)
    assert "science" in results
    assert results["science"] == 2


def test_process_all_skips_non_list_categories(manager):
    config = {"science": [{"name": "r", "url": "https://example.com"}], "metadata": "not-a-list"}
    with patch.object(manager, "clone_repository", return_value=True):
        results = manager.process_all(config)
    assert "science" in results
    assert "metadata" not in results


# ---------------------------------------------------------------------------
# list_repositories
# ---------------------------------------------------------------------------


def test_list_repositories_existing(tmp_path, manager, simple_config):
    # Create one of the repos so it shows as present
    (manager.base_path / "science" / "repo-a").mkdir(parents=True, exist_ok=True)
    # Just verify no exception is raised
    manager.list_repositories(simple_config)


def test_list_repositories_skips_non_list(manager):
    config = {"science": [{"name": "r", "url": "u", "description": "d"}], "meta": "string"}
    manager.list_repositories(config)  # should not raise


# ---------------------------------------------------------------------------
# clean_repositories
# ---------------------------------------------------------------------------


def test_clean_repositories_dry_run(tmp_path, manager, simple_config):
    (manager.base_path / "science" / "orphan-repo").mkdir(parents=True, exist_ok=True)
    manager.clean_repositories(simple_config, dry_run=True)
    # The orphaned directory should NOT be removed during a dry run
    assert (manager.base_path / "science" / "orphan-repo").exists()


def test_clean_repositories_removes_orphan(tmp_path, manager, simple_config):
    orphan = manager.base_path / "science" / "orphan-repo"
    orphan.mkdir(parents=True, exist_ok=True)
    manager.clean_repositories(simple_config, dry_run=False)
    assert not orphan.exists()


def test_clean_repositories_keeps_configured(tmp_path, manager, simple_config):
    configured = manager.base_path / "science" / "repo-a"
    configured.mkdir(parents=True, exist_ok=True)
    manager.clean_repositories(simple_config, dry_run=False)
    assert configured.exists()
