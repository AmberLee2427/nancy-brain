"""Tests for nancy_brain/admin_ui.py utility functions.

These tests only cover the utility functions (not the Streamlit UI) since
the main run_ui() function requires a live Streamlit session to execute.
"""

import os
import sys
import types
import pytest
import yaml
import subprocess
from pathlib import Path
from unittest.mock import patch, MagicMock

# ---------------------------------------------------------------------------
# Setup: mock streamlit and http_api before importing admin_ui
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True, scope="module")
def mock_heavy_deps():
    """Mock streamlit and other heavy dependencies for module-level import."""
    mock_st = MagicMock()
    mock_st.session_state = {}

    # Mock connectors.http_api hierarchy
    mock_http_api_module = types.ModuleType("connectors.http_api")
    mock_streamlit_auth = MagicMock()
    mock_http_api_module.streamlit_auth = mock_streamlit_auth
    mock_http_api_module.auth = MagicMock()

    saved_modules = {}
    modules_to_mock = {
        "streamlit": mock_st,
        "connectors.http_api": mock_http_api_module,
        "connectors.http_api.streamlit_auth": mock_streamlit_auth,
    }
    for k, v in modules_to_mock.items():
        saved_modules[k] = sys.modules.get(k)
        sys.modules[k] = v

    env_patch = patch.dict(os.environ, {"NB_ALLOW_INSECURE": "true"})
    env_patch.start()

    yield mock_st

    env_patch.stop()
    for k, v in saved_modules.items():
        if v is None:
            sys.modules.pop(k, None)
        else:
            sys.modules[k] = v


@pytest.fixture(scope="module")
def admin_ui_module(mock_heavy_deps):
    """Import admin_ui with mocked dependencies."""
    # Remove cached module if it was already imported
    sys.modules.pop("nancy_brain.admin_ui", None)
    import nancy_brain.admin_ui as admin_ui

    return admin_ui


# ---------------------------------------------------------------------------
# load_config
# ---------------------------------------------------------------------------


def test_load_config_existing(tmp_path, admin_ui_module):
    config = {"science": [{"name": "repo1", "url": "https://github.com/org/repo1.git"}]}
    config_file = tmp_path / "repos.yml"
    with open(config_file, "w") as f:
        yaml.safe_dump(config, f)

    result = admin_ui_module.load_config(str(config_file))
    assert result == config


def test_load_config_missing(tmp_path, admin_ui_module):
    result = admin_ui_module.load_config(str(tmp_path / "nonexistent.yml"))
    assert result == {}


# ---------------------------------------------------------------------------
# load_articles_config
# ---------------------------------------------------------------------------


def test_load_articles_config_existing(tmp_path, admin_ui_module):
    config = {"papers": [{"name": "paper1", "url": "https://example.com/p.pdf"}]}
    config_file = tmp_path / "articles.yml"
    with open(config_file, "w") as f:
        yaml.safe_dump(config, f)

    result = admin_ui_module.load_articles_config(str(config_file))
    assert result == config


def test_load_articles_config_missing(tmp_path, admin_ui_module):
    result = admin_ui_module.load_articles_config(str(tmp_path / "nonexistent.yml"))
    assert result == {}


# ---------------------------------------------------------------------------
# save_config
# ---------------------------------------------------------------------------


def test_save_config_creates_file(tmp_path, admin_ui_module):
    config = {"science": [{"name": "repo1", "url": "https://github.com/org/repo1.git"}]}
    config_file = tmp_path / "subdir" / "repos.yml"

    admin_ui_module.save_config(config, str(config_file))
    assert config_file.exists()

    with open(config_file) as f:
        loaded = yaml.safe_load(f)
    assert loaded == config


def test_save_config_raises_on_error(tmp_path, admin_ui_module):
    with pytest.raises(RuntimeError):
        admin_ui_module.save_config({}, "/nonexistent_root/deep/path/repos.yml")


# ---------------------------------------------------------------------------
# save_articles_config
# ---------------------------------------------------------------------------


def test_save_articles_config_creates_file(tmp_path, admin_ui_module):
    config = {"papers": [{"name": "paper1", "url": "https://example.com/p.pdf"}]}
    config_file = tmp_path / "config" / "articles.yml"

    admin_ui_module.save_articles_config(config, str(config_file))
    assert config_file.exists()


# ---------------------------------------------------------------------------
# run_build_command
# ---------------------------------------------------------------------------


def test_run_build_command_no_articles(tmp_path, admin_ui_module):
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0, stdout="ok", stderr="")
        result = admin_ui_module.run_build_command(force_update=False, articles=False)
    cmd = mock_run.call_args[0][0]
    assert "--force-update" not in cmd
    assert "--articles-config" not in cmd


def test_run_build_command_force_update(tmp_path, admin_ui_module):
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        result = admin_ui_module.run_build_command(force_update=True)
    cmd = mock_run.call_args[0][0]
    assert "--force-update" in cmd


def test_run_build_command_with_articles_no_file(tmp_path, admin_ui_module):
    """When articles=True but articles.yml doesn't exist, skip the flag."""
    with patch("subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        with patch("nancy_brain.admin_ui.Path.exists", return_value=False):
            result = admin_ui_module.run_build_command(articles=True)
    cmd = mock_run.call_args[0][0]
    assert "--articles-config" not in cmd


# ---------------------------------------------------------------------------
# _init_session_state_safe
# ---------------------------------------------------------------------------


def test_init_session_state_safe_no_crash(admin_ui_module):
    """Should not raise even if st.session_state is mocked."""
    admin_ui_module._init_session_state_safe()  # Should not raise


# ---------------------------------------------------------------------------
# safe_rerun
# ---------------------------------------------------------------------------


def test_safe_rerun_no_crash(admin_ui_module, mock_heavy_deps):
    """safe_rerun should not raise."""
    # Ensure rerun exists
    mock_heavy_deps.rerun = MagicMock()
    admin_ui_module.safe_rerun()  # Should not raise


def test_safe_rerun_experimental(admin_ui_module, mock_heavy_deps):
    """safe_rerun falls back to experimental_rerun."""
    del mock_heavy_deps.rerun
    mock_heavy_deps.experimental_rerun = MagicMock()
    admin_ui_module.safe_rerun()


# ---------------------------------------------------------------------------
# show_error
# ---------------------------------------------------------------------------


def test_show_error_basic(admin_ui_module):
    """show_error should call st.error and not raise."""
    admin_ui_module.show_error("Test error message")


def test_show_error_with_hint(admin_ui_module):
    """show_error with a hint should call st.info."""
    admin_ui_module.show_error("Error with hint", hint="Try this")


def test_show_error_with_exception(admin_ui_module):
    """show_error with exc should create an expander."""
    exc = ValueError("test error")
    admin_ui_module.show_error("Error with exc", exc=exc)


# ---------------------------------------------------------------------------
# run_ui tests
# ---------------------------------------------------------------------------


class DictLikeState(dict):
    """A dict that also supports attribute-style access (like Streamlit session_state)."""

    def __getattr__(self, key):
        try:
            return self[key]
        except KeyError:
            return None

    def __setattr__(self, key, value):
        self[key] = value


def _setup_mock_st_for_page(mock_st, page_name):
    """Configure mock st for a specific page with allow_insecure=true."""
    session_state = DictLikeState()
    session_state["nb_token"] = None  # Not logged in; NB_ALLOW_INSECURE bypasses auth
    session_state["nb_refresh"] = None
    session_state["search_results"] = []
    session_state["weights_undo_stack"] = []
    mock_st.session_state = session_state

    # Make selectbox return the target page
    mock_st.sidebar.selectbox = MagicMock(return_value=page_name)

    # Make columns return the right number of context-manager mocks
    def make_col():
        col = MagicMock()
        col.__enter__ = MagicMock(return_value=MagicMock())
        col.__exit__ = MagicMock(return_value=False)
        return col

    def mock_columns(n, **kwargs):
        count = n if isinstance(n, int) else len(n)
        return [make_col() for _ in range(count)]

    mock_st.columns = MagicMock(side_effect=mock_columns)

    # expander, form, spinner, etc.
    ctx_mock = MagicMock()
    ctx_mock.__enter__ = MagicMock(return_value=MagicMock())
    ctx_mock.__exit__ = MagicMock(return_value=False)
    mock_st.sidebar.expander = MagicMock(return_value=ctx_mock)
    mock_st.expander = MagicMock(return_value=ctx_mock)
    mock_st.form = MagicMock(return_value=ctx_mock)
    mock_st.spinner = MagicMock(return_value=ctx_mock)

    def mock_tabs(tab_names):
        return [make_col() for _ in tab_names]

    mock_st.tabs = MagicMock(side_effect=mock_tabs)

    # Buttons return False (not pressed) by default
    mock_st.button = MagicMock(return_value=False)
    mock_st.form_submit_button = MagicMock(return_value=False)
    mock_st.checkbox = MagicMock(return_value=False)

    # Text inputs
    mock_st.text_input = MagicMock(return_value="")
    mock_st.number_input = MagicMock(return_value=5)
    mock_st.text_area = MagicMock(return_value="")
    mock_st.selectbox = MagicMock(return_value=None)
    mock_st.file_uploader = MagicMock(return_value=None)  # No file uploaded

    return session_state


def test_run_ui_status_page(admin_ui_module, mock_heavy_deps):
    """run_ui() executes the Status page without errors."""
    with patch.dict(os.environ, {"NB_ALLOW_INSECURE": "true"}):
        _setup_mock_st_for_page(mock_heavy_deps, "📊 Status")
        admin_ui_module.run_ui()  # Should not raise


def test_run_ui_unauthenticated(admin_ui_module, mock_heavy_deps):
    """run_ui() returns early when not authenticated."""
    with patch.dict(os.environ, {"NB_ALLOW_INSECURE": "false"}):
        session_state = DictLikeState()
        session_state["nb_token"] = None
        session_state["nb_refresh"] = None
        session_state["search_results"] = []
        session_state["weights_undo_stack"] = []
        mock_heavy_deps.session_state = session_state

        ctx_mock = MagicMock()
        ctx_mock.__enter__ = MagicMock(return_value=MagicMock())
        ctx_mock.__exit__ = MagicMock(return_value=False)
        mock_heavy_deps.sidebar.expander = MagicMock(return_value=ctx_mock)
        mock_heavy_deps.form = MagicMock(return_value=ctx_mock)
        mock_heavy_deps.form_submit_button = MagicMock(return_value=False)
        mock_heavy_deps.sidebar.selectbox = MagicMock(return_value="📊 Status")
        mock_heavy_deps.button = MagicMock(return_value=False)
        mock_heavy_deps.text_input = MagicMock(return_value="")

        admin_ui_module.run_ui()  # Should return early without rendering pages
        mock_heavy_deps.warning.assert_called()


def test_run_ui_build_page(admin_ui_module, mock_heavy_deps):
    """run_ui() executes the Build page without errors (button not pressed)."""
    with patch.dict(os.environ, {"NB_ALLOW_INSECURE": "true"}):
        _setup_mock_st_for_page(mock_heavy_deps, "🏗️ Build Knowledge Base")
        admin_ui_module.run_ui()


def test_run_ui_repo_management_page(admin_ui_module, mock_heavy_deps):
    """run_ui() executes the Repository Management page without errors."""
    with patch.dict(os.environ, {"NB_ALLOW_INSECURE": "true"}):
        _setup_mock_st_for_page(mock_heavy_deps, "📚 Repository Management")
        admin_ui_module.run_ui()


def test_run_ui_weights_page(admin_ui_module, mock_heavy_deps):
    """run_ui() executes the Weights page without errors."""
    with patch.dict(os.environ, {"NB_ALLOW_INSECURE": "true"}):
        _setup_mock_st_for_page(mock_heavy_deps, "⚖️ Weights")
        admin_ui_module.run_ui()


def test_run_ui_search_page(admin_ui_module, mock_heavy_deps):
    """run_ui() executes the Search page without errors (no search query)."""
    with patch.dict(os.environ, {"NB_ALLOW_INSECURE": "true"}):
        session_state = _setup_mock_st_for_page(mock_heavy_deps, "🔍 Search")
        session_state["search_results"] = []
        session_state["rag_service"] = None
        admin_ui_module.run_ui()
