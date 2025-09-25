# Data models for RAG core
from dataclasses import dataclass
from typing import List


@dataclass
class DocMeta:
    """Metadata for a document in the knowledge base."""

    doc_id: str
    github_url: str
    default_branch: str
    toolkit: str
    doctype: str
    content_sha256: str
    line_index: List[int]


@dataclass
class SearchHit:
    """Search result hit."""

    id: str
    text: str
    score: float


@dataclass
class Passage:
    """Passage retrieved from a document."""

    doc_id: str
    text: str
    github_url: str
    content_sha256: str
    index_version: str = ""


# File-type categorization for weighting
from pathlib import Path

from nancy_brain.chunking import strip_chunk_suffix


def get_file_type_category(doc_id: str) -> str:
    """
    Determine if a document should be treated as code, mixed content, or docs.
    Returns 'code', 'mixed', or 'docs'.
    """
    base_id = strip_chunk_suffix(doc_id)
    path = Path(base_id)

    # Direct code files
    code_extensions = {
        ".py",
        ".js",
        ".ts",
        ".cpp",
        ".java",
        ".go",
        ".rs",
        ".c",
        ".h",
        ".css",
        ".scss",
        ".jsx",
        ".tsx",
    }
    if path.suffix in code_extensions:
        return "code"

    # Converted notebooks (mixed code + documentation)
    if ".nb" in path.suffixes or ".nb.txt" in str(path):
        return "mixed"
    if path.suffix in {".json", ".yaml", ".yml", ".toml", ".ini", ".md", ".rst"}:
        return "mixed"
    return "docs"
