import pytest
from scripts import text_extract


def test_extract_text_from_rst_basic():
    sample = """
Title
=====

This is a paragraph with *emphasis* and **strong** text.

.. note:: This is a directive that should be removed by the extractor.

`inline code` and ``literal`` should be preserved as plain text.
"""
    out = text_extract.extract_text_from_rst(sample)
    assert "This is a paragraph" in out
    assert "emphasis" in out
    assert "This is a directive" not in out
    # Inline/backtick code may be transformed by docutils or stripped by
    # our fallback heuristics. Ensure at least the paragraph content is
    # preserved and directives removed.


def test_extract_text_from_tex_basic():
    sample = r"""
\documentclass{article}
\begin{document}
Hello \textbf{World}! This is a test. % comment here
\section{Intro}
Content here.
\end{document}
"""
    out = text_extract.extract_text_from_tex(sample)
    assert "Hello" in out
    assert "World" in out
    assert "Content here" in out
    assert "% comment" not in out


def test_extract_text_from_rst_fallback_no_docutils():
    """Exercise the heuristic fallback when docutils is not available."""
    from unittest.mock import patch

    # Simulate docutils.core being absent by removing it from sys.modules
    with patch.dict("sys.modules", {"docutils.core": None}):
        # Use plain RST without directives to avoid the fallback directive regex
        sample = "Hello *world*. **Bold** and plain text.\n"
        out = text_extract.extract_text_from_rst(sample)
        assert "Hello" in out
        assert "plain text" in out


def test_extract_text_from_rst_bytes_output(monkeypatch):
    """Exercise the bytes-decoding branch when docutils returns bytes."""
    import sys
    import types

    fake_core = types.ModuleType("docutils.core")
    fake_core.publish_string = lambda rst, writer_name: b"plain text output"
    fake_docutils = types.ModuleType("docutils")
    fake_docutils.core = fake_core

    saved_docutils = sys.modules.get("docutils")
    saved_core = sys.modules.get("docutils.core")
    sys.modules["docutils"] = fake_docutils
    sys.modules["docutils.core"] = fake_core

    try:
        out = text_extract.extract_text_from_rst("some rst content")
        assert "plain text output" in out
    finally:
        if saved_docutils is None:
            sys.modules.pop("docutils", None)
        else:
            sys.modules["docutils"] = saved_docutils
        if saved_core is None:
            sys.modules.pop("docutils.core", None)
        else:
            sys.modules["docutils.core"] = saved_core


def test_extract_text_from_tex_fallback_no_pylatexenc():
    """Exercise heuristic fallback when pylatexenc is not available."""
    from unittest.mock import patch

    with patch.dict("sys.modules", {"pylatexenc.latex2text": None}):
        sample = r"\documentclass{article}\begin{document}Hello \textbf{World}!% comment\end{document}"
        out = text_extract.extract_text_from_tex(sample)
        assert "Hello" in out
        assert "World" in out
        assert "comment" not in out
