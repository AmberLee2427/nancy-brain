"""Streamlit-friendly authentication helper for Nancy Brain HTTP API.

This module provides small helper functions that talk to the HTTP API
(login/refresh). It also contains a convenience Streamlit UI function
`render_streamlit_ui()` for running the login page standalone. The module
avoids executing Streamlit UI on import so it can be imported by other
modules (like `nancy_brain/admin_ui`).
"""

from __future__ import annotations

import os
from typing import Dict, Optional

import requests

# Default to localhost; users can override with environment variable NB_API_URL
DEFAULT_API_URL = os.environ.get("NB_API_URL", "http://127.0.0.1:8000")


def get_api_url() -> str:
    """Return the API URL to use (env NB_API_URL overrides default)."""
    return os.environ.get("NB_API_URL", DEFAULT_API_URL)


def login(username: str, password: str, api_url: Optional[str] = None) -> Dict:
    """Call the HTTP API /login endpoint and return parsed JSON on success.

    Raises requests.HTTPError on non-200 responses.
    """
    api_url = api_url or get_api_url()
    resp = requests.post(f"{api_url.rstrip('/')}/login", data={"username": username, "password": password})
    if resp.status_code != 200:
        resp.raise_for_status()
    return resp.json()


def refresh(refresh_token: str, api_url: Optional[str] = None) -> Dict:
    """Call the HTTP API /refresh endpoint and return parsed JSON on success.

    Raises requests.HTTPError on non-200 responses.
    """
    api_url = api_url or get_api_url()
    resp = requests.post(f"{api_url.rstrip('/')}/refresh", json={"refresh_token": refresh_token})
    if resp.status_code != 200:
        resp.raise_for_status()
    return resp.json()


def render_streamlit_ui():
    """Render a small Streamlit login page (when running this module standalone).

    This function intentionally imports Streamlit lazily so importing the
    module doesn't execute UI code.
    """
    import streamlit as st

    API_URL = get_api_url()

    st.title("Nancy Brain Admin — Login")

    if "token" not in st.session_state:
        st.session_state.token = None
    if "refresh_token" not in st.session_state:
        st.session_state.refresh_token = None

    with st.form("login_form"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Login")
        if submitted:
            try:
                data = login(username, password, api_url=API_URL)
                st.session_state.token = data.get("access_token")
                st.session_state.refresh_token = data.get("refresh_token")
                st.success("Logged in")
            except Exception as e:  # pragma: no cover - runtime UI error
                st.error(f"Login failed: {e}")

    if st.session_state.get("token"):
        st.write("You are logged in.")
        col1, col2 = st.columns(2)
        if col1.button("Call protected endpoint"):
            headers = {"Authorization": f"Bearer {st.session_state.token}"}
            r = requests.get(f"{API_URL.rstrip('/')}/protected", headers=headers)
            st.write(r.status_code, r.text)
        if col2.button("Refresh access token"):
            try:
                r = refresh(st.session_state.refresh_token, api_url=API_URL)
                st.session_state.token = r.get("access_token")
                st.success("Access token refreshed")
            except Exception as e:  # pragma: no cover - runtime UI error
                st.error(f"Refresh failed: {e}")


if __name__ == "__main__":
    # Allow running this module directly for a minimal login page
    try:
        render_streamlit_ui()
    except Exception:  # keep standalone usage robust
        import traceback

        traceback.print_exc()
