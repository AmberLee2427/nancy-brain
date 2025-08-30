"""Nancy Brain Web UI - Simple admin interface for knowledge base management."""

import asyncio
from pathlib import Path
from typing import Optional

import streamlit as st
import yaml
import subprocess
import sys
import os
import logging
import traceback

# Add package root to path
package_root = Path(__file__).parent.parent
sys.path.insert(0, str(package_root))

from rag_core.service import RAGService

from connectors.http_api import streamlit_auth
import re
import html

try:
    # Prefer relative import when running as a package
    from .utils_weights import validate_weights_config
except Exception:
    # Fallback to absolute import when running the module as a script
    from nancy_brain.utils_weights import validate_weights_config

from nancy_brain.weights_persistence import load_model_weights, save_model_weights, set_model_weight


def _init_session_state_safe():
    """Initialize Streamlit session state keys when running under Streamlit.

    This function swallows errors so importing the module in non-Streamlit
    contexts (tests) doesn't fail.
    """
    try:
        if "search_results" not in st.session_state:
            st.session_state.search_results = []
        if "nb_token" not in st.session_state:
            st.session_state.nb_token = None
        if "nb_refresh" not in st.session_state:
            st.session_state.nb_refresh = None
        if "weights_undo_stack" not in st.session_state:
            # each entry: (doc_id, previous_value) where previous_value may be None
            st.session_state.weights_undo_stack = []
    except Exception:
        # Not running inside Streamlit; ignore
        pass


def safe_rerun():
    """Try to call Streamlit's experimental rerun; fallback to an instruction message if unavailable."""
    try:
        # Some Streamlit versions provide experimental_rerun, others may not
        getattr(st, "experimental_rerun")()
    except Exception:
        try:
            # Newer API may expose experimental functions under runtime; try best-effort
            st.info("Please refresh the page to apply changes.")
        except Exception:
            # Silently ignore when not running in Streamlit
            pass


def show_error(message: str, exc: Exception = None, hint: str = None):
    """Display a user-friendly error with optional exception details and a hint."""
    logging.exception(message)
    st.error(message)
    if hint:
        st.info(f"Hint: {hint}")
    if exc is not None:
        with st.expander("Error details"):
            st.text(traceback.format_exc())


def load_config(config_path: str = "config/repositories.yml"):
    """Load repository configuration."""
    try:
        with open(config_path, "r") as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        return {}


def load_articles_config(config_path: str = "config/articles.yml"):
    """Load articles configuration."""
    try:
        with open(config_path, "r") as f:
            return yaml.safe_load(f)
    except FileNotFoundError:
        return {}


def save_config(config: dict, config_path: str = "config/repositories.yml"):
    """Save repository configuration."""
    try:
        os.makedirs(os.path.dirname(config_path), exist_ok=True)
        with open(config_path, "w") as f:
            yaml.dump(config, f, default_flow_style=False)
    except Exception as e:
        raise RuntimeError(f"Failed to save repositories config to {config_path}: {e}") from e


def save_articles_config(config: dict, config_path: str = "config/articles.yml"):
    """Save articles configuration."""
    try:
        os.makedirs(os.path.dirname(config_path), exist_ok=True)
        with open(config_path, "w") as f:
            yaml.dump(config, f, default_flow_style=False, sort_keys=False)
    except Exception as e:
        raise RuntimeError(f"Failed to save articles config to {config_path}: {e}") from e


def run_build_command(force_update: bool = False, articles: bool = False):
    """Run the knowledge base build command."""
    cmd = [
        sys.executable,
        str(package_root / "scripts" / "build_knowledge_base.py"),
        "--config",
        "config/repositories.yml",
        "--embeddings-path",
        "knowledge_base/embeddings",
    ]

    if articles and Path("config/articles.yml").exists():
        cmd.extend(["--articles-config", "config/articles.yml"])

    if force_update:
        cmd.append("--force-update")

    return subprocess.run(cmd, capture_output=True, text=True, cwd=package_root)


def run_ui():
    """Render the Streamlit admin UI. Call this from a script entrypoint.

    Keeping UI rendering inside a function avoids executing Streamlit code at
    import time (which breaks tests that import this module).
    """
    st.set_page_config(page_title="Nancy Brain Admin", page_icon="🧠", layout="wide")

    _init_session_state_safe()

    # Main UI
    st.title("🧠 Nancy Brain Admin")
    st.markdown("*Turn GitHub repos into AI-searchable knowledge bases*")

    # Sidebar navigation + auth
    st.sidebar.title("Navigation")
    allow_insecure = os.environ.get("NB_ALLOW_INSECURE", "false").lower() in ("1", "true", "yes")

    with st.sidebar.expander("🔒 Authentication", expanded=True):
        if st.session_state.nb_token:
            st.write("**Logged in**")
            if st.button("Logout"):
                st.session_state.nb_token = None
                st.session_state.nb_refresh = None
                safe_rerun()
        else:
            st.write("Login to access admin features")
            with st.form("sidebar_login"):
                su = st.text_input("Username", key="_login_user")
                sp = st.text_input("Password", type="password", key="_login_pass")
                if st.form_submit_button("Login"):
                    try:
                        data = streamlit_auth.login(su, sp)
                        st.session_state.nb_token = data.get("access_token")
                        st.session_state.nb_refresh = data.get("refresh_token")
                        st.success("Logged in")
                        safe_rerun()
                    except Exception as e:
                        st.error(f"Login failed: {e}")

        if allow_insecure:
            st.info("NB_ALLOW_INSECURE is set: auth bypass enabled")

    page = st.sidebar.selectbox(
        "Choose a page:",
        ["🔍 Search", "⚖️ Weights", "📚 Repository Management", "🏗️ Build Knowledge Base", "📊 Status"],
    )

    is_authenticated = bool(st.session_state.nb_token) or allow_insecure

    if not is_authenticated:
        st.warning("You must be logged in to use the admin UI. Use the sidebar to login.")
        return

    if page == "🔍 Search":
        st.header("🔍 Search Knowledge Base")

        # Search interface
        col1, col2 = st.columns([3, 1])
        with col1:
            query = st.text_input("Search query:", placeholder="Enter your search query...")
        with col2:
            limit = st.number_input("Results:", min_value=1, max_value=20, value=5)

        # (Reweighting configuration moved below search results)

        # Ensure a single RAGService is created and reused (embeddings are heavy to load)
        if "rag_service" not in st.session_state or st.session_state.rag_service is None:
            try:
                # Use a dedicated model_weights file for thumbs persistence
                st.session_state.rag_service = RAGService(
                    embeddings_path=Path("knowledge_base/embeddings"),
                    config_path=Path("config/repositories.yml"),
                    weights_path=Path("config/model_weights.yaml"),
                )
            except Exception as e:
                # Don't crash the UI; show an error and leave rag_service as None
                st.session_state.rag_service = None
                show_error("Failed to initialize RAGService", e)

        if st.button("🔍 Search") and query:
            with st.spinner("Searching..."):
                try:
                    service = st.session_state.rag_service
                    if service is None:
                        st.error("Search service is not available")
                    else:
                        results = asyncio.run(service.search_docs(query, limit=limit))
                        st.session_state.search_results = results
                except Exception as e:
                    st.error(f"Search failed: {e}")

        # Display results
        if st.session_state.search_results:
            st.subheader("Search Results")

            def _highlight_snippet(text: str, query: str, snippet_len: int = 400, highlights: list = None) -> str:
                """Return an HTML highlighted snippet for the query tokens.

                Uses <mark> tags around matches and returns an HTML string (escaped).
                """
                if not text:
                    return ""

                escaped = html.escape(text)

                # If highlights provided by the service, use their offsets (preferred)
                if highlights:
                    # Build HTML by slicing original escaped text using offsets
                    parts = []
                    last = 0
                    for h in highlights:
                        s = max(0, h.get("start", 0))
                        e = min(len(text), h.get("end", s))
                        # Escape bounds in case
                        parts.append(html.escape(text[last:s]))
                        span = html.escape(text[s:e])
                        typ = h.get("type", "fuzzy")
                        color = "#ffd54f" if typ == "exact" else ("#90caf9" if typ == "stem" else "#e1bee7")
                        parts.append(f"<mark style='background:{color}; padding:0;'>{span}</mark>")
                        last = e
                    parts.append(html.escape(text[last:]))
                    composed = "".join(parts)

                    # Focus snippet around first highlight
                    m = re.search(r"<mark", composed)
                    if m:
                        idx = max(0, m.start() - snippet_len // 2)
                        snippet = composed[idx : idx + snippet_len]
                        if idx > 0:
                            snippet = "..." + snippet
                        if idx + snippet_len < len(composed):
                            snippet = snippet + "..."
                        return snippet
                    else:
                        return composed[:snippet_len] + ("..." if len(composed) > snippet_len else "")

                # Tokenize query into words, ignore very short tokens
                tokens = [t for t in re.split(r"\s+", query.strip()) if len(t) > 0]
                if not tokens:
                    return html.escape(text[:snippet_len]) + ("..." if len(text) > snippet_len else "")

                # Escape text for HTML then perform case-insensitive replacement
                escaped = html.escape(text)

                # Build a regex that matches any token (word-boundary aware)
                pattern = r"(" + r"|".join(re.escape(t) for t in tokens) + r")"

                def _repl(m):
                    return f"<mark>{m.group(0)}</mark>"

                try:
                    highlighted = re.sub(pattern, _repl, escaped, flags=re.IGNORECASE)
                except re.error:
                    # Fallback if regex fails
                    highlighted = escaped

                # Find first highlighted occurrence to build a focused snippet
                first_match = re.search(r"<mark>", highlighted)
                if first_match:
                    idx = first_match.start()
                    # Map back to original escaped text positions roughly
                    start = max(0, idx - snippet_len // 2)
                    end = start + snippet_len
                    snippet = highlighted[start:end]
                    if start > 0:
                        snippet = "..." + snippet
                    if end < len(highlighted):
                        snippet = snippet + "..."
                    return snippet
                else:
                    # No match highlighted (rare), return escaped leading chunk
                    return escaped[:snippet_len] + ("..." if len(escaped) > snippet_len else "")

            for i, result in enumerate(st.session_state.search_results, 1):
                title = f"{i}. {result.get('id', 'unknown')} (score: {result.get('score', 0):.3f})"
                with st.expander(title):
                    snippet_html = _highlight_snippet(
                        result.get("text", ""), query or "", highlights=result.get("highlights", [])
                    )
                    # Show snippet as HTML
                    st.markdown(snippet_html, unsafe_allow_html=True)
                    # Full highlighted content in an expander
                    with st.expander("Show full result"):
                        full_html = _highlight_snippet(
                            result.get("text", ""),
                            query or "",
                            snippet_len=len(result.get("text", "")),
                            highlights=result.get("highlights", []),
                        )
                        st.markdown(full_html, unsafe_allow_html=True)

                    # Thumbs up / Thumbs down controls to persist model_weights (left aligned)
                    col_left, col_right, _ = st.columns([0.12, 0.12, 1])
                    model_weights_path = Path("config/model_weights.yaml")
                    service = st.session_state.get("rag_service")

                    def _persist_model_weight(doc_id: str, new_value: float):
                        try:
                            # Load previous value and persist using helper
                            prev = set_model_weight(model_weights_path, doc_id, float(new_value))
                            # record undo
                            try:
                                st.session_state.weights_undo_stack.append((doc_id, prev))
                            except Exception:
                                pass
                            # Update in-memory search weights as well
                            if service is not None and hasattr(service, "search"):
                                try:
                                    service.search.model_weights[doc_id] = float(new_value)
                                except Exception:
                                    pass
                            st.success(f"Updated weight for {doc_id} -> {new_value}")
                        except Exception as e:
                            show_error("Failed to persist model weight", e)

                    # Upvote (increase multiplier by 20%, cap at 2.0)
                    with col_left:
                        if st.button("👍", key=f"thumbs_up_{i}"):
                            doc_id = result.get("id")
                            # Determine current value from service or disk
                            cur = 1.0
                            if service and hasattr(service, "search"):
                                cur = float(service.search.model_weights.get(doc_id, cur))
                            # Compute new value
                            new = min(2.0, cur * 1.2)
                            _persist_model_weight(doc_id, new)
                    # Downvote (decrease multiplier by 20%, floor at 0.5)
                    with col_right:
                        if st.button("👎", key=f"thumbs_down_{i}"):
                            doc_id = result.get("id")
                            cur = 1.0
                            if service and hasattr(service, "search"):
                                cur = float(service.search.model_weights.get(doc_id, cur))
                            new = max(0.5, cur * 0.8)
                            _persist_model_weight(doc_id, new)

    # New dedicated Weights page: always-visible editors for index_weights and model_weights
    elif page == "⚖️ Weights":
        st.header("⚖️ Reweighting / Model Weights")

        # --- Reweighting configuration editor
        st.markdown("---")
        st.markdown("#### Reweighting Configuration (index_weights.yaml)")
        weights_path = Path("config/index_weights.yaml")
        try:
            if weights_path.exists():
                with open(weights_path, "r") as wf:
                    weights_cfg = yaml.safe_load(wf) or {}
            else:
                weights_cfg = {}
        except Exception as e:
            weights_cfg = {}
            show_error("Failed to load index_weights.yaml", e, hint="Check config directory and YAML syntax")

        ext_weights = weights_cfg.get("extensions", {})
        path_includes = weights_cfg.get("path_includes", {})

        with st.form("weights_form"):
            st.markdown("**Extension weights (file extension -> multiplier)**")
            ext_text = st.text_area(
                "Extensions YAML (e.g. .py: 1.0)", value=yaml.dump(ext_weights) if ext_weights else "", height=120
            )
            st.markdown("**Path includes (keyword -> multiplier)**")
            path_text = st.text_area(
                "Path includes YAML (e.g. tests: 1.1)",
                value=yaml.dump(path_includes) if path_includes else "",
                height=120,
            )
            if st.form_submit_button("Save weights"):
                try:
                    new_ext = yaml.safe_load(ext_text) or {}
                    new_path = yaml.safe_load(path_text) or {}
                    new_cfg = {"extensions": new_ext, "path_includes": new_path}
                    os.makedirs(weights_path.parent, exist_ok=True)
                    # Validate before saving
                    ok, errs = validate_weights_config(new_cfg)
                    if not ok:
                        for e in errs:
                            st.error(e)
                    else:
                        with open(weights_path, "w") as wf:
                            yaml.dump(new_cfg, wf, default_flow_style=False, sort_keys=False)
                        st.success("Saved index_weights.yaml")
                        safe_rerun()
                except Exception as e:
                    show_error("Failed to save index_weights.yaml", e, hint="Ensure YAML is valid and file is writable")

        # Export / Import reweighting configuration (outside the form)
        try:
            export_weights_yaml = yaml.dump(
                weights_cfg if weights_cfg else {}, default_flow_style=False, sort_keys=False
            )
        except Exception:
            export_weights_yaml = ""

        col_exp, col_imp = st.columns(2)
        with col_exp:
            st.download_button(
                "⬇️ Export Reweighting Config",
                data=export_weights_yaml,
                file_name="index_weights_export.yml",
                mime="text/yaml",
                key="export_index_weights",
            )
        with col_imp:
            upload_weights = st.file_uploader(
                "⬆️ Import Reweighting Config", type=["yml", "yaml"], key="upload_index_weights_top"
            )
            if upload_weights is not None:
                try:
                    raw = upload_weights.read()
                    txt = raw.decode("utf-8")
                    parsed = yaml.safe_load(txt)
                    if not isinstance(parsed, dict):
                        st.error("Imported weights must be a YAML mapping")
                    else:
                        if st.button("Import and overwrite weights"):
                            # Validate parsed config
                            ok, errs = validate_weights_config(parsed)
                            if not ok:
                                for e in errs:
                                    st.error(e)
                            else:
                                os.makedirs(weights_path.parent, exist_ok=True)
                                with open(weights_path, "w") as wf:
                                    yaml.dump(parsed, wf, default_flow_style=False, sort_keys=False)
                                st.success("Imported index_weights.yaml")
                                safe_rerun()
                except Exception as e:
                    show_error("Failed to parse uploaded weights YAML.", e, hint="Ensure file is valid YAML")

        # --- Model weights editor (per-document multipliers)
        st.markdown("---")
        st.markdown("#### Model Weights (per-document) - config/model_weights.yaml")
        model_weights_path = Path("config/model_weights.yaml")
        try:
            if model_weights_path.exists():
                with open(model_weights_path, "r") as mf:
                    model_weights_cfg = yaml.safe_load(mf) or {}
            else:
                model_weights_cfg = {}
        except Exception as e:
            model_weights_cfg = {}
            show_error("Failed to load model_weights.yaml", e, hint="Check YAML syntax")

        # Show editable mapping
        model_text = yaml.dump(model_weights_cfg) if isinstance(model_weights_cfg, dict) else "{}"
        with st.form("model_weights_form"):
            st.markdown("**Per-document model weights (doc_id -> multiplier)**")
            model_text_area = st.text_area(
                "Model weights YAML (e.g. cat1/repo/path: 1.2)", value=model_text, height=200
            )
            col_save = st.columns([1])[0]
            with col_save:
                if st.form_submit_button("Save model weights"):
                    try:
                        parsed = yaml.safe_load(model_text_area) or {}
                        if not isinstance(parsed, dict):
                            st.error("Model weights must be a YAML mapping of doc_id -> numeric multiplier")
                        else:
                            # Coerce values to floats and clamp to safe range
                            fixed = {}
                            for k, v in parsed.items():
                                try:
                                    f = float(v)
                                except Exception:
                                    st.error(f"Invalid numeric value for {k}: {v}")
                                    raise
                                # Clamp to reasonable bounds [0.5, 2.0]
                                f = max(0.5, min(2.0, f))
                                fixed[k] = f
                            # Save using helper
                            save_model_weights(fixed, model_weights_path)
                            # Update in-memory service if available
                            svc = st.session_state.get("rag_service")
                            if svc is not None and hasattr(svc, "search"):
                                try:
                                    svc.search.model_weights = dict(fixed)
                                except Exception:
                                    pass
                            st.success("Saved model_weights.yaml")
                    except Exception as e:
                        show_error(
                            "Failed to save model_weights.yaml", e, hint="Ensure YAML is valid and values are numeric"
                        )

        # Undo / Export / Import actions (must be outside the form)
        if st.button("Undo last weight change"):
            stack = st.session_state.get("weights_undo_stack", [])
            if not stack:
                st.info("Nothing to undo")
            else:
                doc_id, prev = stack.pop()
                # prev may be None (meaning the doc_id didn't exist before)
                try:
                    set_model_weight(model_weights_path, doc_id, prev)
                    # update in-memory service
                    svc = st.session_state.get("rag_service")
                    if svc is not None and hasattr(svc, "search"):
                        try:
                            if prev is None:
                                svc.search.model_weights.pop(doc_id, None)
                            else:
                                svc.search.model_weights[doc_id] = float(prev)
                        except Exception:
                            pass
                    st.success(f"Reverted {doc_id} to {prev}")
                except Exception as e:
                    show_error("Failed to undo model weight change", e)

        # Export / Import reweighting configuration (index_weights export only)
        try:
            export_weights_yaml = yaml.dump(
                weights_cfg if weights_cfg else {}, default_flow_style=False, sort_keys=False
            )
        except Exception:
            export_weights_yaml = ""

        col_exp, col_imp = st.columns(2)
        with col_exp:
            st.download_button(
                "⬇️ Export Reweighting Config",
                data=export_weights_yaml,
                file_name="index_weights_export.yml",
                mime="text/yaml",
                key="export_index_weights_bottom",
            )
        with col_imp:
            upload_weights = st.file_uploader(
                "⬆️ Import Reweighting Config", type=["yml", "yaml"], key="upload_index_weights_bottom"
            )
            if upload_weights is not None:
                try:
                    raw = upload_weights.read()
                    txt = raw.decode("utf-8")
                    parsed = yaml.safe_load(txt)
                    if not isinstance(parsed, dict):
                        st.error("Imported weights must be a YAML mapping")
                    else:
                        if st.button("Import and overwrite weights"):
                            # Validate parsed config
                            ok, errs = validate_weights_config(parsed)
                            if not ok:
                                for e in errs:
                                    st.error(e)
                            else:
                                os.makedirs(weights_path.parent, exist_ok=True)
                                with open(weights_path, "w") as wf:
                                    yaml.dump(parsed, wf, default_flow_style=False, sort_keys=False)
                                st.success("Imported index_weights.yaml")
                                safe_rerun()
                except Exception as e:
                    show_error("Failed to parse uploaded weights YAML.", e, hint="Ensure file is valid YAML")

    elif page == "📚 Repository Management":
        st.header("📚 Repository Management")

        # Create tabs for repositories and articles
        tab1, tab2 = st.tabs(["📁 Repositories", "📄 Articles"])

        with tab1:
            st.subheader("GitHub Repositories")

            # (Reweighting configuration moved to the Search page)

            # Load current config
            config = load_config()

            # Add new repository
            st.markdown("#### Add New Repository")
            with st.form("add_repo"):
                col1, col2 = st.columns(2)
                with col1:
                    category = st.text_input("Category:", placeholder="e.g., microlensing_tools")
                    repo_name = st.text_input("Repository Name:", placeholder="e.g., MulensModel")
                with col2:
                    repo_url = st.text_input("Repository URL:", placeholder="https://github.com/user/repo.git")
                    description = st.text_input("Description (optional):", placeholder="Brief description")

                if st.form_submit_button("➕ Add Repository"):
                    if category and repo_name and repo_url:
                        try:
                            if category not in config:
                                config[category] = []

                            new_repo = {"name": repo_name, "url": repo_url}
                            if description:
                                new_repo["description"] = description

                            config[category].append(new_repo)
                            save_config(config)
                            st.success(f"Added {repo_name} to {category}")
                            safe_rerun()
                        except Exception as e:
                            show_error(
                                "Failed to add repository.",
                                e,
                                hint="Check file permissions and YAML validity for config/repositories.yml",
                            )
                    else:
                        st.error("Please fill in category, name, and URL")

            # Export / Import configuration
            st.markdown("#### Export / Import Configuration")
            try:
                export_yaml = yaml.dump(config if config else {}, default_flow_style=False, sort_keys=False)
            except Exception:
                export_yaml = ""

            st.download_button(
                label="⬇️ Export Repositories Config",
                data=export_yaml,
                file_name="repositories_export.yml",
                mime="text/yaml",
                key="export_repositories",
            )

            uploaded = st.file_uploader("⬆️ Import Repositories Config (YAML)", type=["yml", "yaml"], key="upload_repos")
            if uploaded is not None:
                try:
                    raw = uploaded.read()
                    text = raw.decode("utf-8")
                    parsed = yaml.safe_load(text)

                    if not isinstance(parsed, dict):
                        st.error("Imported file is not a valid repositories mapping (expected YAML mapping).")
                    else:
                        st.info("Preview of imported config (first 1000 chars):")
                        st.code(text[:1000])
                        if st.button("Import and overwrite repositories config"):
                            save_config(parsed)
                            st.success("Repositories configuration imported successfully.")
                            safe_rerun()
                except Exception as e:
                    show_error(
                        "Failed to parse uploaded repositories YAML.",
                        e,
                        hint="Ensure the file is valid YAML and not too large",
                    )

            # Display current repositories
            st.markdown("#### Current Repositories")
            if config:
                for category, repos in config.items():
                    st.write(f"**{category}**")
                    for repo in repos:
                        col1, col2, col3 = st.columns([3, 2, 1])
                        with col1:
                            st.write(f"• {repo['name']}")
                        with col2:
                            st.write(repo.get("description", ""))
                        with col3:
                            if st.button("🗑️", key=f"delete_repo_{category}_{repo['name']}"):
                                try:
                                    config[category] = [r for r in config[category] if r["name"] != repo["name"]]
                                    if not config[category]:
                                        del config[category]
                                    save_config(config)
                                    safe_rerun()
                                except Exception as e:
                                    show_error(
                                        "Failed to delete repository.",
                                        e,
                                        hint="Ensure the config file is writable and valid YAML",
                                    )
            else:
                st.info("No repositories configured yet.")

        with tab2:
            st.subheader("PDF Articles")

            # Load current articles config
            articles_config = load_articles_config()

            # Add new article
            st.markdown("#### Add New Article")
            with st.form("add_article"):
                col1, col2 = st.columns(2)
                with col1:
                    article_category = st.text_input(
                        "Category:",
                        placeholder="e.g., foundational_papers",
                        key="article_category",
                    )
                    article_name = st.text_input(
                        "Article Name:",
                        placeholder="e.g., Paczynski_1986_microlensing",
                        key="article_name",
                    )
                with col2:
                    article_url = st.text_input(
                        "Article URL:",
                        placeholder="https://arxiv.org/pdf/paper.pdf",
                        key="article_url",
                    )
                    article_description = st.text_input(
                        "Description:",
                        placeholder="Brief description of the article",
                        key="article_description",
                    )

                if st.form_submit_button("➕ Add Article"):
                    if article_category and article_name and article_url:
                        try:
                            if article_category not in articles_config:
                                articles_config[article_category] = []

                            # Check if article already exists
                            existing = [a for a in articles_config[article_category] if a.get("name") == article_name]
                            if existing:
                                st.error(f"Article '{article_name}' already exists in category '{article_category}'")
                            else:
                                new_article = {"name": article_name, "url": article_url}
                                if article_description:
                                    new_article["description"] = article_description

                                articles_config[article_category].append(new_article)
                                save_articles_config(articles_config)
                                st.success(f"Added article '{article_name}' to category '{article_category}'")
                                safe_rerun()
                        except Exception as e:
                            show_error(
                                "Failed to add article.",
                                e,
                                hint="Check file permissions and YAML validity for config/articles.yml",
                            )
                    else:
                        st.error("Please fill in category, name, and URL")

            # Display current articles
            st.markdown("#### Current Articles")
            if articles_config:
                for category, articles in articles_config.items():
                    st.write(f"**{category}**")
                    for article in articles:
                        col1, col2, col3 = st.columns([3, 2, 1])
                        with col1:
                            st.write(f"• {article['name']}")
                            if "url" in article:
                                st.markdown(f"  [{article['url']}]({article['url']})")
                        with col2:
                            st.write(article.get("description", ""))
                        with col3:
                            if st.button("🗑️", key=f"delete_article_{category}_{article['name']}"):
                                try:
                                    articles_config[category] = [
                                        a for a in articles_config[category] if a["name"] != article["name"]
                                    ]
                                    if not articles_config[category]:
                                        del articles_config[category]
                                    save_articles_config(articles_config)
                                    safe_rerun()
                                except Exception as e:
                                    show_error(
                                        "Failed to delete article.",
                                        e,
                                        hint="Ensure config/articles.yml is writable and valid YAML",
                                    )
            else:
                st.info("No articles configured yet.")

            # Export / Import articles configuration
            st.markdown("#### Export / Import Articles Configuration")
            try:
                export_articles_yaml = yaml.dump(
                    articles_config if articles_config else {}, default_flow_style=False, sort_keys=False
                )
            except Exception:
                export_articles_yaml = ""

            st.download_button(
                label="⬇️ Export Articles Config",
                data=export_articles_yaml,
                file_name="articles_export.yml",
                mime="text/yaml",
                key="export_articles",
            )

            uploaded_articles = st.file_uploader(
                "⬆️ Import Articles Config (YAML)", type=["yml", "yaml"], key="upload_articles"
            )
            if uploaded_articles is not None:
                try:
                    raw = uploaded_articles.read()
                    text = raw.decode("utf-8")
                    parsed = yaml.safe_load(text)

                    if not isinstance(parsed, dict):
                        st.error("Imported file is not a valid articles mapping (expected YAML mapping).")
                    else:
                        st.info("Preview of imported articles config (first 1000 chars):")
                        st.code(text[:1000])
                        if st.button("Import and overwrite articles config"):
                            save_articles_config(parsed)
                            st.success("Articles configuration imported successfully.")
                            safe_rerun()
                except Exception as e:
                    show_error(
                        "Failed to parse uploaded articles YAML.",
                        e,
                        hint="Ensure the file is valid YAML and not too large",
                    )

    elif page == "🏗️ Build Knowledge Base":
        st.header("🏗️ Build Knowledge Base")

        col1, col2 = st.columns(2)
        with col1:
            force_update = st.checkbox("Force update existing repositories")
            include_articles = st.checkbox("Include PDF articles (if configured)")

        with col2:
            st.info(
                "**Build Options:**\n- Force update: Re-downloads all repositories\n- Include articles: Downloads PDFs from articles.yml"
            )

        if st.button("🚀 Start Build"):
            st.info("Starting build — streaming output below. This may take several minutes.")

            # Build command (same as run_build_command)
            cmd = [
                sys.executable,
                str(package_root / "scripts" / "build_knowledge_base.py"),
                "--config",
                "config/repositories.yml",
                "--embeddings-path",
                "knowledge_base/embeddings",
            ]
            if include_articles and Path("config/articles.yml").exists():
                cmd.extend(["--articles-config", "config/articles.yml"])
            if force_update:
                cmd.append("--force-update")

            # Run subprocess and stream stdout to the UI with a progress bar
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                cwd=package_root,
            )

            log_box = st.empty()
            progress = st.progress(0)

            lines = []
            progress_val = 0

            # Read lines as they become available and update UI
            try:
                while True:
                    line = process.stdout.readline()
                    if line == "" and process.poll() is not None:
                        break
                    if line:
                        # Append and keep recent output trimmed
                        lines.append(line)
                        if len(lines) > 500:
                            lines = lines[-500:]

                        # Detect structured progress markers emitted by the build script
                        stripped = line.strip()
                        if stripped.startswith("PROGRESS_JSON:"):
                            try:
                                payload = stripped.split("PROGRESS_JSON:", 1)[1].strip()
                                obj = __import__("json").loads(payload)
                                pct = int(obj.get("percent", 0))
                                progress.progress(max(progress_val, min(100, pct)))
                                progress_val = max(progress_val, min(100, pct))
                                # Optionally include stage detail in log
                                lines.append(f"[progress] {obj.get('stage', '')}: {obj.get('detail', '')}\n")
                            except Exception:
                                pass
                        else:
                            # Heuristic fallback increment if no structured progress seen
                            progress_val = min(100, progress_val + 1)
                            progress.progress(progress_val)

                        # Update log area
                        log_box.text("".join(lines[-200:]))

                returncode = process.poll()
            except Exception as e:
                process.kill()
                st.error(f"Build process failed: {e}")
                return

            # Finalize progress and show results
            progress.progress(100)
            if returncode == 0:
                st.success("✅ Knowledge base built successfully!")
                if lines:
                    with st.expander("Build Output"):
                        st.text("".join(lines))
            else:
                st.error(f"❌ Build failed (exit code {returncode})")
                if lines:
                    with st.expander("Build Output"):
                        st.text("".join(lines))

    elif page == "📊 Status":
        st.header("📊 System Status")

        # Check if embeddings exist
        embeddings_path = Path("knowledge_base/embeddings")
        config_path = Path("config/repositories.yml")
        articles_path = Path("config/articles.yml")
        weights_path = Path("config/weights.yaml")

        col1, col2, col3 = st.columns(3)

        with col1:
            st.subheader("Files")
            st.write("📁 Embeddings:", "✅" if embeddings_path.exists() else "❌")
            st.write("⚙️ Repositories Config:", "✅" if config_path.exists() else "❌")
            st.write("📄 Articles Config:", "✅" if articles_path.exists() else "❌")
            st.write("⚖️ Weights:", "✅" if weights_path.exists() else "❌")

        with col2:
            st.subheader("Knowledge Base")
            if embeddings_path.exists():
                try:
                    # Try to count files in embeddings
                    index_files = list(embeddings_path.glob("**/*"))
                    st.write(f"📄 Index files: {len(index_files)}")
                except Exception:
                    st.write("📄 Index files: Unknown")
            else:
                st.write("📄 Index files: No embeddings found")

        with col3:
            st.subheader("Configuration")
            config = load_config()
            articles_config = load_articles_config()

            total_repos = sum(len(repos) for repos in config.values()) if config else 0
            total_articles = sum(len(articles) for articles in articles_config.values()) if articles_config else 0

            st.write(f"📚 Total repositories: {total_repos}")
            st.write(f"📄 Total articles: {total_articles}")
            st.write(f"📁 Repository categories: {len(config) if config else 0}")
            st.write(f"📁 Article categories: {len(articles_config) if articles_config else 0}")

    # Footer
    st.markdown("---")
    st.markdown("*Nancy Brain - AI-powered knowledge base for research*")


if __name__ == "__main__":
    run_ui()
