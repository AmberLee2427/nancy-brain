from pathlib import Path
from unittest.mock import patch

import requests
import yaml

from nancy_brain.config_validation import validate_repositories_config
from nancy_brain.env_import import import_from_env


class MockResponse:
    def __init__(self, payload, status_code=200):
        self.payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")

    def json(self):
        return self.payload


def _write_env(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def _read_yaml(path: Path):
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def test_parse_conda_env(tmp_path):
    env_file = tmp_path / "environment.yml"
    output_file = tmp_path / "repositories.yml"
    _write_env(
        env_file,
        """
name: survey_env
dependencies:
  - python=3.12
  - pip
  - pip:
    - alpha_pkg==1.0.0
    - beta_pkg>=2.0
""",
    )

    responses = [
        MockResponse({"info": {"project_urls": {"Source": "https://github.com/org-a/repo-a"}}}),
        MockResponse({"info": {"project_urls": {"Repository": "https://github.com/org-b/repo-b.git"}}}),
    ]

    with patch("nancy_brain.env_import.requests.get", side_effect=responses) as mock_get:
        with patch("nancy_brain.env_import.time.sleep", return_value=None):
            result = import_from_env(env_file, category=None, output_path=output_file, dry_run=False)

    assert result["added"] == 2
    assert result["errors"] == []
    assert mock_get.call_count == 2
    assert mock_get.call_args_list[0].args[0] == "https://pypi.org/pypi/alpha_pkg/json"
    assert mock_get.call_args_list[1].args[0] == "https://pypi.org/pypi/beta_pkg/json"

    config = _read_yaml(output_file)
    assert "survey_env" in config
    assert len(config["survey_env"]) == 2


def test_github_url_resolved(tmp_path):
    env_file = tmp_path / "environment.yml"
    output_file = tmp_path / "repositories.yml"
    _write_env(
        env_file,
        """
name: demo_env
dependencies:
  - pip:
    - mypkg
""",
    )

    payload = {
        "info": {"project_urls": {"Source": "https://github.com/Owner-Name/Repo-Name/tree/main?tab=readme#section"}}
    }

    with patch("nancy_brain.env_import.requests.get", return_value=MockResponse(payload)):
        with patch("nancy_brain.env_import.time.sleep", return_value=None):
            result = import_from_env(env_file, category=None, output_path=output_file, dry_run=False)

    assert result["added"] == 1
    config = _read_yaml(output_file)
    entry = config["demo_env"][0]
    assert entry["url"] == "https://github.com/Owner-Name/Repo-Name"
    assert entry["name"] == "owner_name_repo_name"
    assert entry["description"] == "mypkg - source from PyPI project_urls"


def test_no_github_url_skipped(tmp_path):
    env_file = tmp_path / "environment.yml"
    output_file = tmp_path / "repositories.yml"
    _write_env(
        env_file,
        """
name: no_github
dependencies:
  - pip:
    - plainpkg
""",
    )

    payload = {"info": {"project_urls": {"Documentation": "https://example.com/docs"}}}

    with patch("nancy_brain.env_import.requests.get", return_value=MockResponse(payload)):
        with patch("nancy_brain.env_import.time.sleep", return_value=None):
            result = import_from_env(env_file, category=None, output_path=output_file, dry_run=False)

    assert result["added"] == 0
    assert result["skipped_no_github"] == 1
    assert result["errors"] == []


def test_editable_install_skipped(tmp_path):
    env_file = tmp_path / "environment.yml"
    output_file = tmp_path / "repositories.yml"
    _write_env(
        env_file,
        """
name: editable_env
dependencies:
  - pip:
    - -e .
""",
    )

    with patch("nancy_brain.env_import.requests.get") as mock_get:
        with patch("nancy_brain.env_import.time.sleep", return_value=None):
            result = import_from_env(env_file, category=None, output_path=output_file, dry_run=False)

    assert result["added"] == 0
    assert result["skipped_no_github"] == 0
    assert result["skipped_duplicate"] == 0
    assert result["errors"] == []
    mock_get.assert_not_called()


def test_duplicate_url_skipped(tmp_path):
    env_file = tmp_path / "environment.yml"
    output_file = tmp_path / "repositories.yml"
    _write_env(
        env_file,
        """
name: dup_env
dependencies:
  - pip:
    - dup_pkg
""",
    )

    payload = {"info": {"project_urls": {"Source": "https://github.com/acme/reusable-repo"}}}

    with patch("nancy_brain.env_import.requests.get", return_value=MockResponse(payload)):
        with patch("nancy_brain.env_import.time.sleep", return_value=None):
            first = import_from_env(env_file, category=None, output_path=output_file, dry_run=False)

    with patch("nancy_brain.env_import.requests.get", return_value=MockResponse(payload)):
        with patch("nancy_brain.env_import.time.sleep", return_value=None):
            second = import_from_env(env_file, category=None, output_path=output_file, dry_run=False)

    assert first["added"] == 1
    assert second["added"] == 0
    assert second["skipped_duplicate"] == 1


def test_ref_field_validation():
    valid_cfg = {"cat": [{"name": "repo1", "url": "https://github.com/org/repo1", "ref": "v1.0.0"}]}
    ok_valid, errors_valid = validate_repositories_config(valid_cfg)
    assert ok_valid
    assert errors_valid == []

    invalid_cfg = {"cat": [{"name": "repo2", "url": "https://github.com/org/repo2", "ref": "   "}]}
    ok_invalid, errors_invalid = validate_repositories_config(invalid_cfg)
    assert not ok_invalid
    assert any("'ref' must be a non-empty string" in err for err in errors_invalid)


def test_ref_field_absent_passes():
    cfg = {"cat": [{"name": "repo", "url": "https://github.com/org/repo"}]}
    ok, errors = validate_repositories_config(cfg)
    assert ok
    assert errors == []


def test_dry_run_no_write(tmp_path):
    env_file = tmp_path / "environment.yml"
    output_file = tmp_path / "repositories.yml"
    _write_env(
        env_file,
        """
name: dry_run_env
dependencies:
  - pip:
    - dryrun_pkg
""",
    )

    payload = {"info": {"project_urls": {"Source": "https://github.com/acme/dryrun"}}}

    with patch("nancy_brain.env_import.requests.get", return_value=MockResponse(payload)):
        with patch("nancy_brain.env_import.time.sleep", return_value=None):
            result = import_from_env(env_file, category=None, output_path=output_file, dry_run=True)

    assert result["added"] == 1
    assert not output_file.exists()


def test_category_override(tmp_path):
    env_file = tmp_path / "environment.yml"
    output_file = tmp_path / "repositories.yml"
    _write_env(
        env_file,
        """
name: original_env_name
dependencies:
  - pip:
    - category_pkg
""",
    )

    payload = {"info": {"project_urls": {"Source": "https://github.com/acme/cat-repo"}}}

    with patch("nancy_brain.env_import.requests.get", return_value=MockResponse(payload)):
        with patch("nancy_brain.env_import.time.sleep", return_value=None):
            result = import_from_env(env_file, category="my_cat", output_path=output_file, dry_run=False)

    assert result["added"] == 1
    config = _read_yaml(output_file)
    assert "my_cat" in config
    assert "original_env_name" not in config


def test_home_page_fallback(tmp_path):
    """Packages with no project_urls but a GitHub home_page are still imported."""
    env_file = tmp_path / "environment.yml"
    output_file = tmp_path / "repositories.yml"
    _write_env(
        env_file,
        """
name: test_env
dependencies:
  - pip:
    - old_pkg==1.0.0
""",
    )

    # Package exposes GitHub URL only via home_page (pre-2020 style)
    payload = {"info": {"project_urls": None, "home_page": "https://github.com/org/legacy-repo"}}

    with patch("nancy_brain.env_import.requests.get", return_value=MockResponse(payload)):
        with patch("nancy_brain.env_import.time.sleep", return_value=None):
            result = import_from_env(env_file, category=None, output_path=output_file, dry_run=False)

    assert result["added"] == 1
    config = _read_yaml(output_file)
    category = list(config.keys())[0]
    assert config[category][0]["url"] == "https://github.com/org/legacy-repo"


# ---------------------------------------------------------------------------
# Additional tests for improved coverage
# ---------------------------------------------------------------------------

from nancy_brain.env_import import (
    _is_skippable_pip_spec,
    _package_name_from_pip_spec,
    _normalize_github_url,
    _extract_github_url,
    _iter_existing_urls,
    _version_from_pip_spec,
    _parse_requirements_lines,
    import_from_requirements,
    import_from_pyproject,
    import_from_file,
)


def test_is_skippable_empty():
    assert _is_skippable_pip_spec("") is True
    assert _is_skippable_pip_spec("   ") is True


def test_is_skippable_dot():
    assert _is_skippable_pip_spec(".") is True


def test_is_skippable_http():
    assert _is_skippable_pip_spec("https://example.com/pkg.tar.gz") is True


def test_is_skippable_git_plus():
    assert _is_skippable_pip_spec("git+https://github.com/org/repo.git") is True


def test_is_skippable_double_dash():
    assert _is_skippable_pip_spec("--no-deps") is True


def test_package_name_from_pip_spec_starts_with_dash():
    assert _package_name_from_pip_spec("-e .") is None


def test_package_name_from_pip_spec_hyphen_name():
    # A normal package name
    result = _package_name_from_pip_spec("numpy>=1.0")
    assert result == "numpy"


def test_normalize_github_url_non_github():
    result = _normalize_github_url("https://gitlab.com/owner/repo")
    assert result is None


def test_normalize_github_url_no_https():
    result = _normalize_github_url("github.com/owner/repo")
    assert result == "https://github.com/owner/repo"


def test_normalize_github_url_git_plus_prefix():
    result = _normalize_github_url("git+https://github.com/owner/myrepo.git")
    assert result == "https://github.com/owner/myrepo"


def test_normalize_github_url_empty():
    assert _normalize_github_url("") is None
    assert _normalize_github_url(None) is None


def test_extract_github_url_not_github_url():
    payload = {"info": {"project_urls": {"Homepage": "https://gitlab.com/owner/repo"}, "home_page": ""}}
    result = _extract_github_url(payload)
    assert result is None


def test_extract_github_url_non_priority_key():
    """Non-priority key with github url should be found."""
    payload = {
        "info": {
            "project_urls": {
                "Source": "https://other.com/page",
                "BugTracker": "https://github.com/owner/repo/issues",
            }
        }
    }
    result = _extract_github_url(payload)
    # Should find github url from BugTracker (non-priority key)
    assert result is not None


def test_iter_existing_urls_non_github_url():
    config = {"science": [{"name": "repo1", "url": "https://bitbucket.org/org/repo"}]}
    urls = _iter_existing_urls(config)
    assert "https://bitbucket.org/org/repo" in urls


def test_iter_existing_urls_non_list_entries():
    config = {"science": "not-a-list"}
    urls = _iter_existing_urls(config)
    assert len(urls) == 0


def test_iter_existing_urls_empty_url():
    config = {"science": [{"name": "repo", "url": ""}]}
    urls = _iter_existing_urls(config)
    assert len(urls) == 0


# ---------------------------------------------------------------------------
# Version pinning
# ---------------------------------------------------------------------------


def test_version_from_pip_spec_exact():
    assert _version_from_pip_spec("numpy==1.24.0") == "1.24.0"


def test_version_from_pip_spec_no_pin():
    assert _version_from_pip_spec("numpy>=1.24.0") is None
    assert _version_from_pip_spec("numpy") is None


def test_pin_versions_adds_ref(tmp_path):
    env_file = tmp_path / "environment.yml"
    output_file = tmp_path / "repositories.yml"
    _write_env(
        env_file,
        """
name: pinned_env
dependencies:
  - pip:
    - mypkg==3.2.1
""",
    )

    payload = {"info": {"project_urls": {"Source": "https://github.com/org/mypkg"}}}

    with patch("nancy_brain.env_import.requests.get", return_value=MockResponse(payload)):
        with patch("nancy_brain.env_import.time.sleep", return_value=None):
            result = import_from_env(env_file, category=None, output_path=output_file, pin_versions=True)

    assert result["added"] == 1
    config = _read_yaml(output_file)
    entry = config["pinned_env"][0]
    assert entry["ref"] == "3.2.1"


def test_no_pin_versions_no_ref(tmp_path):
    env_file = tmp_path / "environment.yml"
    output_file = tmp_path / "repositories.yml"
    _write_env(
        env_file,
        """
name: unpinned_env
dependencies:
  - pip:
    - mypkg==3.2.1
""",
    )

    payload = {"info": {"project_urls": {"Source": "https://github.com/org/mypkg"}}}

    with patch("nancy_brain.env_import.requests.get", return_value=MockResponse(payload)):
        with patch("nancy_brain.env_import.time.sleep", return_value=None):
            result = import_from_env(env_file, category=None, output_path=output_file, pin_versions=False)

    assert result["added"] == 1
    config = _read_yaml(output_file)
    entry = config["unpinned_env"][0]
    assert "ref" not in entry


# ---------------------------------------------------------------------------
# requirements.txt
# ---------------------------------------------------------------------------


def test_parse_requirements_lines_basic():
    lines = [
        "numpy==1.24.0",
        "scipy>=1.10",
        "# this is a comment",
        "",
        "-r other.txt",
        "--extra-index-url https://example.com",
        "requests",
    ]
    result = _parse_requirements_lines(lines)
    assert result == ["numpy==1.24.0", "scipy>=1.10", "requests"]


def test_parse_requirements_lines_inline_comment():
    lines = ["numpy==1.24.0  # pinned for stability"]
    result = _parse_requirements_lines(lines)
    assert result == ["numpy==1.24.0"]


def test_requirements_txt_import(tmp_path):
    req_file = tmp_path / "requirements.txt"
    output_file = tmp_path / "repositories.yml"
    req_file.write_text("numpy==1.24.0\nscipy>=1.10\n", encoding="utf-8")

    responses = [
        MockResponse({"info": {"project_urls": {"Source": "https://github.com/numpy/numpy"}}}),
        MockResponse({"info": {"project_urls": {"Source": "https://github.com/scipy/scipy"}}}),
    ]

    with patch("nancy_brain.env_import.requests.get", side_effect=responses):
        with patch("nancy_brain.env_import.time.sleep"):
            result = import_from_requirements(req_file, category=None, output_path=output_file)

    assert result["added"] == 2
    config = _read_yaml(output_file)
    # Default category = stem of filename
    assert "requirements" in config


def test_requirements_txt_pin_versions(tmp_path):
    req_file = tmp_path / "requirements.txt"
    output_file = tmp_path / "repositories.yml"
    req_file.write_text("numpy==1.24.0\n", encoding="utf-8")

    payload = {"info": {"project_urls": {"Source": "https://github.com/numpy/numpy"}}}
    with patch("nancy_brain.env_import.requests.get", return_value=MockResponse(payload)):
        with patch("nancy_brain.env_import.time.sleep"):
            result = import_from_requirements(req_file, category=None, output_path=output_file, pin_versions=True)

    assert result["added"] == 1
    entry = _read_yaml(output_file)["requirements"][0]
    assert entry["ref"] == "1.24.0"


# ---------------------------------------------------------------------------
# pyproject.toml
# ---------------------------------------------------------------------------


def _write_pyproject(path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def test_pyproject_pep621_import(tmp_path):
    toml_file = tmp_path / "pyproject.toml"
    output_file = tmp_path / "repositories.yml"
    _write_pyproject(
        toml_file,
        '[project]\nname = "myproject"\ndependencies = ["requests==2.31.0"]\n',
    )

    payload = {"info": {"project_urls": {"Source": "https://github.com/psf/requests"}}}
    with patch("nancy_brain.env_import.requests.get", return_value=MockResponse(payload)):
        with patch("nancy_brain.env_import.time.sleep"):
            result = import_from_pyproject(toml_file, category=None, output_path=output_file)

    assert result["added"] == 1
    config = _read_yaml(output_file)
    # Category should be the project name
    assert "myproject" in config


def test_pyproject_pep621_pin_versions(tmp_path):
    toml_file = tmp_path / "pyproject.toml"
    output_file = tmp_path / "repositories.yml"
    _write_pyproject(
        toml_file,
        '[project]\nname = "myproject"\ndependencies = ["requests==2.31.0"]\n',
    )

    payload = {"info": {"project_urls": {"Source": "https://github.com/psf/requests"}}}
    with patch("nancy_brain.env_import.requests.get", return_value=MockResponse(payload)):
        with patch("nancy_brain.env_import.time.sleep"):
            result = import_from_pyproject(toml_file, category=None, output_path=output_file, pin_versions=True)

    assert result["added"] == 1
    entry = _read_yaml(output_file)["myproject"][0]
    assert entry["ref"] == "2.31.0"


def test_pyproject_poetry_import(tmp_path):
    toml_file = tmp_path / "pyproject.toml"
    output_file = tmp_path / "repositories.yml"
    _write_pyproject(
        toml_file,
        '[tool.poetry]\nname = "mypoetryproject"\n\n'
        '[tool.poetry.dependencies]\npython = "^3.11"\nnumpy = "^1.24.0"\n',
    )

    payload = {"info": {"project_urls": {"Source": "https://github.com/numpy/numpy"}}}
    with patch("nancy_brain.env_import.requests.get", return_value=MockResponse(payload)):
        with patch("nancy_brain.env_import.time.sleep"):
            result = import_from_pyproject(toml_file, category=None, output_path=output_file)

    assert result["added"] == 1
    config = _read_yaml(output_file)
    assert "mypoetryproject" in config


def test_pyproject_poetry_python_skipped(tmp_path):
    """The 'python' dependency entry in Poetry config should be silently skipped."""
    toml_file = tmp_path / "pyproject.toml"
    output_file = tmp_path / "repositories.yml"
    _write_pyproject(
        toml_file,
        '[tool.poetry]\nname = "proj"\n\n' '[tool.poetry.dependencies]\npython = "^3.11"\n',
    )

    with patch("nancy_brain.env_import.requests.get") as mock_get:
        with patch("nancy_brain.env_import.time.sleep"):
            result = import_from_pyproject(toml_file, category=None, output_path=output_file)

    mock_get.assert_not_called()
    assert result["added"] == 0


# ---------------------------------------------------------------------------
# Auto-detect dispatcher
# ---------------------------------------------------------------------------


def test_auto_detect_conda_env(tmp_path):
    env_file = tmp_path / "environment.yml"
    output_file = tmp_path / "repositories.yml"
    _write_env(
        env_file,
        "name: myenv\ndependencies:\n  - pip:\n    - somepkg\n",
    )

    payload = {"info": {"project_urls": {"Source": "https://github.com/org/somepkg"}}}
    with patch("nancy_brain.env_import.requests.get", return_value=MockResponse(payload)):
        with patch("nancy_brain.env_import.time.sleep"):
            result = import_from_file(env_file, output_path=output_file)

    assert result["added"] == 1


def test_auto_detect_requirements_txt(tmp_path):
    req_file = tmp_path / "requirements.txt"
    output_file = tmp_path / "repositories.yml"
    req_file.write_text("somepkg==1.0.0\n", encoding="utf-8")

    payload = {"info": {"project_urls": {"Source": "https://github.com/org/somepkg"}}}
    with patch("nancy_brain.env_import.requests.get", return_value=MockResponse(payload)):
        with patch("nancy_brain.env_import.time.sleep"):
            result = import_from_file(req_file, output_path=output_file)

    assert result["added"] == 1


def test_auto_detect_pyproject_toml(tmp_path):
    toml_file = tmp_path / "pyproject.toml"
    output_file = tmp_path / "repositories.yml"
    _write_pyproject(
        toml_file,
        '[project]\nname = "p"\ndependencies = ["somepkg==1.0.0"]\n',
    )

    payload = {"info": {"project_urls": {"Source": "https://github.com/org/somepkg"}}}
    with patch("nancy_brain.env_import.requests.get", return_value=MockResponse(payload)):
        with patch("nancy_brain.env_import.time.sleep"):
            result = import_from_file(toml_file, output_path=output_file)

    assert result["added"] == 1


def test_auto_detect_unknown_raises(tmp_path):
    import pytest

    unknown = tmp_path / "deps.xyz"
    unknown.write_text("", encoding="utf-8")
    with pytest.raises(ValueError, match="Unrecognised file format"):
        import_from_file(unknown, output_path=tmp_path / "repositories.yml")
