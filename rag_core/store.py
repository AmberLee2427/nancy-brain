"""
Store for document embeddings.
"""

# imports
import json
from pathlib import Path
import sqlite3
from typing import Optional


class Store:
    """Store for reading document text by line ranges."""

    def __init__(self, base_path: Path):
        """Initialize store with base directory for text files."""
        self.base_path = base_path

    def _read_indexed_document(self, doc_id: str) -> Optional[str]:
        """Reconstruct a source document from its indexed chunks."""
        db_path = self.base_path / "embeddings" / "index" / "documents"
        if not db_path.exists():
            return None

        escaped_id = doc_id.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        try:
            conn = sqlite3.connect(str(db_path))
        except sqlite3.Error:
            return None

        try:
            rows = conn.execute(
                """
                SELECT id, text, tags
                FROM sections
                WHERE id = ? OR id LIKE ? ESCAPE '\\'
                ORDER BY id
                """,
                (doc_id, f"{escaped_id}#chunk-%"),
            ).fetchall()
        except sqlite3.Error:
            return None
        finally:
            conn.close()

        chunks = []
        for indexed_id, text, tags_json in rows:
            try:
                tags = json.loads(tags_json or "{}")
            except (TypeError, ValueError):
                tags = {}
            source_document = tags.get("source_document")
            if source_document and source_document != doc_id:
                continue
            chunks.append(
                {
                    "id": indexed_id,
                    "text": text or "",
                    "index": int(tags.get("chunk_index", len(chunks))),
                    "start": tags.get("span_start"),
                    "end": tags.get("span_end"),
                }
            )

        if not chunks:
            return None

        chunks.sort(key=lambda chunk: (chunk["index"], chunk["id"]))
        if not all(isinstance(chunk["start"], int) and isinstance(chunk["end"], int) for chunk in chunks):
            return "\n".join(chunk["text"] for chunk in chunks)

        document_parts = []
        cursor = 0
        for chunk in chunks:
            start = max(chunk["start"], cursor)
            if start > cursor:
                document_parts.append("\n" * (start - cursor))
            text = chunk["text"]
            document_parts.append(text)
            cursor = max(chunk["end"], start + len(text))
        return "".join(document_parts)

    def read_lines(self, doc_id: str, start: Optional[int] = None, end: Optional[int] = None) -> str:
        """Read lines from a document. If start and end are None, return full content."""
        # Try the doc_id as-is first, then with .txt extension
        doc_path = self.base_path / doc_id
        if not doc_path.exists():
            doc_path = self.base_path / f"{doc_id}.txt"
        if doc_path.exists():
            with open(doc_path, "r") as f:
                text = f.read()
        else:
            text = self._read_indexed_document(doc_id)
            if text is None:
                raise FileNotFoundError(f"Document not found: {doc_id}")

        lines = text.splitlines(keepends=True)
        # Default to full range
        s = start if start is not None else 0
        e = end if end is not None else len(lines)
        return "".join(lines[s:e])
