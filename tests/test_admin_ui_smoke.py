import sys
import types
import importlib
import pytest

from tests.helpers.streamlit_stub import make_streamlit_stub, StreamlitStubException


def test_admin_ui_smoke_headless(monkeypatch):
    monkeypatch.setenv("NB_ALLOW_INSECURE", "true")

    # Remove any pre-imported real streamlit modules and admin_ui
    for k in list(sys.modules.keys()):
        if k == "streamlit" or k.startswith("streamlit."):
            sys.modules.pop(k, None)
    sys.modules.pop("nancy_brain.admin_ui", None)

    # Insert stub and minimal emojis module
    stub = make_streamlit_stub()
    sys.modules["streamlit"] = stub
    emojis_mod = types.ModuleType("streamlit.emojis")
    emojis_mod.ALL_EMOJIS = {}
    sys.modules["streamlit.emojis"] = emojis_mod

    admin_ui = importlib.import_module("nancy_brain.admin_ui")
    # Should run without raising StreamlitStubException
    admin_ui.run_ui()


def test_button_in_form_detected():
    # Ensure stubbed streamlit is used
    for k in list(sys.modules.keys()):
        if k == "streamlit" or k.startswith("streamlit."):
            sys.modules.pop(k, None)
    stub = make_streamlit_stub()
    sys.modules["streamlit"] = stub

    # code that incorrectly places a button inside a form should trigger the stub
    bad_code = """
import streamlit as st
with st.form('f'):
    st.button('bad')
"""
    mod = types.ModuleType("tmp_mod")
    with pytest.raises(StreamlitStubException):
        exec(bad_code, mod.__dict__)


def test_duplicate_download_detected():
    for k in list(sys.modules.keys()):
        if k == "streamlit" or k.startswith("streamlit."):
            sys.modules.pop(k, None)
    stub = make_streamlit_stub()
    sys.modules["streamlit"] = stub

    import streamlit as st

    # first call ok
    st.download_button("label", data="x", file_name="a", mime="t")
    # second call should raise
    with pytest.raises(StreamlitStubException):
        st.download_button("label", data="x", file_name="a", mime="t")
