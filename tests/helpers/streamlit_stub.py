"""Reusable minimal Streamlit stub for headless UI tests.

Provides a factory `make_streamlit_stub()` and the
`StreamlitStubException` used by test suites to simulate
Streamlit widget API and to detect misuse (buttons in forms,
duplicate download buttons, missing attributes).
"""

import types


class StreamlitStubException(Exception):
    pass


def make_streamlit_stub():
    mod = types.ModuleType("streamlit")

    # simple session state dict-like
    class SessionState(dict):
        def __getattr__(self, item):
            return self.get(item)

    mod.session_state = SessionState()

    # tracking flags and element ids
    mod._inside_form = False
    mod._download_ids = set()

    # basic no-op UI functions
    def set_page_config(**kwargs):
        return None

    def title(*a, **k):
        return None

    def header(*a, **k):
        return None

    def subheader(*a, **k):
        return None

    def markdown(*a, **k):
        return None

    def info(*a, **k):
        return None

    def error(*a, **k):
        return None

    def success(*a, **k):
        return None

    def text(*a, **k):
        return None

    def write(*a, **k):
        return None

    def text_input(*a, **k):
        return ""

    def number_input(*a, **k):
        return k.get("value", 1)

    def text_area(*a, **k):
        return k.get("value", "")

    def file_uploader(*a, **k):
        return None

    # simple context managers
    class _Ctx:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    def spinner(msg=None):
        return _Ctx()

    def expander(msg=None, **k):
        return _Ctx()

    def columns(spec):
        # return list of _Ctx-like column placeholders
        if isinstance(spec, (list, tuple)):
            n = len(spec)
        elif isinstance(spec, int):
            n = spec
        else:
            n = 1
        return [_Ctx() for _ in range(n)]

    def form(name):
        class FormCtx:
            def __enter__(self_inner):
                mod._inside_form = True
                return self_inner

            def __exit__(self_inner, exc_type, exc, tb):
                mod._inside_form = False
                return False

        return FormCtx()

    def form_submit_button(label=None):
        # default: not submitted
        return False

    def button(label=None, key=None):
        # Raise if used inside a form (simulate Streamlit behaviour)
        if mod._inside_form:
            raise StreamlitStubException("st.button() can't be used inside st.form()")
        return False

    def download_button(label, data=None, file_name=None, mime=None, key=None):
        # detect duplicates: if key provided, use key; otherwise signature of args
        sig = key if key is not None else (label, file_name, mime)
        if sig in mod._download_ids:
            raise StreamlitStubException("Duplicate download_button element id")
        mod._download_ids.add(sig)
        return False

    # sidebar object
    class Sidebar:
        def expander(self, *a, **k):
            return _Ctx()

        def selectbox(self, *_a, **_k):
            # default to weights page so editors render
            return "⚖️ Weights"

        def title(self, *a, **k):
            return None

    mod.sidebar = Sidebar()

    # attach functions
    mod.set_page_config = set_page_config
    mod.title = title
    mod.header = header
    mod.subheader = subheader
    mod.markdown = markdown
    mod.info = info
    mod.error = error
    mod.success = success
    mod.text = text
    mod.write = write
    mod.text_input = text_input
    mod.number_input = number_input
    mod.text_area = text_area
    mod.file_uploader = file_uploader
    mod.spinner = spinner
    mod.expander = expander
    mod.columns = columns
    mod.form = form
    mod.form_submit_button = form_submit_button
    mod.button = button
    mod.download_button = download_button

    # provide a minimal emojis module attribute to avoid internal imports
    mod.emojis = types.SimpleNamespace(ALL_EMOJIS={})

    return mod
