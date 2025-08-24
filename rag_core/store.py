"""
Store for document embeddings.
"""

# imports
from pathlib import Path
from typing import Optional


class Store:
    """Store for reading document text by line ranges."""

    def __init__(self, base_path: Path):
        """Initialize store with base directory for text files."""
        self.base_path = base_path

    # I really don't understand what is suppose to go in here

    def read_lines(self, doc_id: str, start: Optional[int] = None, end: Optional[int] = None) -> str:
        """Read lines from a document. If start and end are None, return full content."""
        # Try the doc_id as-is first, then with .txt extension
        doc_path = self.base_path / doc_id
        if not doc_path.exists():
            doc_path = self.base_path / f"{doc_id}.txt"
        if not doc_path.exists():
            raise FileNotFoundError(f"Document not found: {doc_id}")

        # Read all lines including newline characters
        with open(doc_path, "r") as f:
            lines = f.readlines()
        # Default to full range
        s = start if start is not None else 0
        e = end if end is not None else len(lines)
        return "".join(lines[s:e])
