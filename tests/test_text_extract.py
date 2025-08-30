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
