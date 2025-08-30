"""
Lightweight text extractors for .rst and .tex content.

Prefer optional libraries (docutils, pylatexenc) when available. Fall back to
best-effort heuristics otherwise to avoid heavy optional dependencies in CI.
"""

from typing import Optional
import re


def extract_text_from_rst(rst: str) -> str:
    """Convert reStructuredText to plain text.

    Uses docutils if available; otherwise applies simple heuristics to strip
    common RST markup (directives, roles, inline markup).
    """
    try:
        from docutils.core import publish_string

        # docutils returns bytes when writer_name='pseudoxml' or 'plaintext'
        out = publish_string(rst, writer_name="plaintext")
        if isinstance(out, bytes):
            try:
                return out.decode("utf-8").strip()
            except Exception:
                return out.decode(errors="ignore").strip()
        return str(out).strip()
    except Exception:
        # Fallback heuristic
        text = rst
        # Remove reST directives (lines starting with ".. ") and their content blocks
        text = re.sub(r"(?m)^\.\. .*$(?:\n^(?:\s+.*$))*", "", text)
        # Remove role markup :role:`text`
        text = re.sub(r":\w+:`([^`]+)`", r"\1", text)
        # Replace inline literal backticks ``like this`` or `like this`
        text = re.sub(r"``([^`]+)``", r"\1", text)
        text = re.sub(r"`([^`]+)`", r"\1", text)
        # Remove simple interpreted text (``..``) and emphasis/strong markers
        text = text.replace("**", "").replace("*", "")
        # Remove heading underlines/overlines (common in rst)
        text = re.sub(r"(?m)^[-=~`\^\"']{2,}\s*$", "", text)
        # Collapse multiple blank lines
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()


def extract_text_from_tex(tex: str) -> str:
    """Convert LaTeX content into plain text.

    Uses pylatexenc if available; otherwise applies heuristic stripping of
    macros and environments.
    """
    try:
        from pylatexenc.latex2text import LatexNodes2Text

        return LatexNodes2Text().latex_to_text(tex).strip()
    except Exception:
        text = tex
        # Remove comments
        text = re.sub(r"%.*$", "", text, flags=re.MULTILINE)
    # Keep inner text of common environments: replace \begin{env}...\end{env} with the inner content
    text = re.sub(r"\\begin\{[^}]+\}(.*?)\\end\{[^}]+\}", r"\1", text, flags=re.DOTALL)
    # Replace commands like \command[opt]{arg} or \command{arg} with their argument text
    text = re.sub(r"\\[a-zA-Z]+\*?(?:\[[^\]]*\])?\{([^}]*)\}", r"\1", text)
    # Remove remaining simple commands like \command
    text = re.sub(r"\\[a-zA-Z]+\*?(?:\[[^\]]*\])?", "", text)
    # Collapse multiple whitespace
    text = re.sub(r"\s+", " ", text)
    return text.strip()


__all__ = ["extract_text_from_rst", "extract_text_from_tex"]
