"""Utility helpers for chunking source documents before embedding."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional
import os
import re

__all__ = [
    "Chunk",
    "SmartChunker",
    "strip_chunk_suffix",
]


@dataclass
class Chunk:
    """Represents a chunk of text prepared for embedding."""

    chunk_id: str
    text: str
    metadata: Dict[str, object]


_CHUNK_MARKERS = ("#chunk-", "::chunk-", "|chunk:", "@chunk:")


def strip_chunk_suffix(doc_id: str) -> str:
    """Strip any chunk suffix that may have been appended to an identifier."""
    if not doc_id:
        return doc_id
    base = doc_id
    for marker in _CHUNK_MARKERS:
        idx = base.find(marker)
        if idx != -1:
            base = base[:idx]
    return base


_CODE_EXTENSIONS = {
    ".py",
    ".js",
    ".ts",
    ".tsx",
    ".jsx",
    ".java",
    ".c",
    ".cpp",
    ".cc",
    ".h",
    ".hpp",
    ".go",
    ".rs",
    ".swift",
    ".kt",
    ".m",
    ".cs",
}

_MIXED_EXTENSIONS = {
    ".md",
    ".rst",
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".ini",
    ".tex",
}


class SmartChunker:
    """Heuristic chunker that keeps chunks semantically coherent."""

    def __init__(
        self,
        text_chunk_chars: int = 1400,
        text_overlap_chars: int = 220,
        code_chunk_lines: Optional[int] = None,
        code_overlap_lines: Optional[int] = None,
        min_index_chars: int = 60,
    ) -> None:
        self.text_chunk_chars = text_chunk_chars
        self.text_overlap_chars = text_overlap_chars

        # Allow environment overrides for code chunk sizing
        if code_chunk_lines is None:
            env_lines = os.environ.get("SMART_CHUNK_CODE_LINES")
            if env_lines:
                try:
                    code_chunk_lines = max(1, int(env_lines))
                except ValueError:
                    code_chunk_lines = None
        if code_chunk_lines is None:
            code_chunk_lines = 80

        if code_overlap_lines is None:
            env_overlap = os.environ.get("SMART_CHUNK_CODE_OVERLAP")
            if env_overlap:
                try:
                    code_overlap_lines = max(0, int(env_overlap))
                except ValueError:
                    code_overlap_lines = None
        if code_overlap_lines is None:
            code_overlap_lines = 10

        # Prevent pathological configurations
        if code_overlap_lines >= code_chunk_lines:
            code_overlap_lines = max(0, code_chunk_lines - 1)

        self.code_chunk_lines = code_chunk_lines
        self.code_overlap_lines = code_overlap_lines
        self.min_index_chars = max(0, min_index_chars)
        self._text_boundary_lookahead = 180
        self._code_boundary_lookahead = 0  # unused with simplified chunking

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def chunk(
        self,
        doc_id: str,
        content: str,
        *,
        category: Optional[str] = None,
        source_kind: Optional[str] = None,
    ) -> List[Chunk]:
        """Split *content* into embedding-ready chunks."""
        if content is None:
            return []
        text = content.replace("\r\n", "\n").replace("\r", "\n")
        text = text.strip("\n")
        if not text.strip():
            return []

        base_doc_id = strip_chunk_suffix(doc_id)
        inferred_category = category or self._infer_category(base_doc_id)

        if self._should_skip(base_doc_id, text, inferred_category):
            return []

        if inferred_category == "code":
            chunks = self._chunk_code(base_doc_id, text)
        else:
            chunks = self._chunk_text(base_doc_id, text, inferred_category)

        total = len(chunks)
        for idx, chunk in enumerate(chunks):
            meta = chunk.metadata
            meta.setdefault("chunk_index", idx)
            meta["chunk_count"] = total
            meta.setdefault("category", inferred_category)
            meta.setdefault("source_document", base_doc_id)
            if source_kind:
                meta.setdefault("source_kind", source_kind)
            if "token_estimate" not in meta:
                meta["token_estimate"] = self._estimate_tokens(chunk.text)
        return chunks

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _infer_category(self, doc_id: str) -> str:
        suffix = Path(doc_id).suffix.lower()
        if suffix in _CODE_EXTENSIONS:
            return "code"
        if suffix in _MIXED_EXTENSIONS:
            return "mixed"
        if ".nb" in Path(doc_id).suffixes or doc_id.endswith(".nb.txt"):
            return "mixed"
        return "docs"

    def _should_skip(self, doc_id: str, content: str, category: str) -> bool:
        stripped = content.strip()
        if not stripped:
            return True
        if len(stripped) < self.min_index_chars:
            important = {"readme", "license", "notice", "changelog"}
            name = Path(doc_id).name.lower()
            if not any(name.startswith(token) for token in important):
                if category == "code":
                    return True
                if len(stripped.split()) < 4:
                    return True
        if category == "code":
            name = Path(doc_id).name
            code_lines = [ln for ln in stripped.splitlines() if ln.strip() and not ln.strip().startswith("#")]
            if name == "__init__.py" and len(code_lines) <= 2:
                return True
            if len(code_lines) <= 1 and len(stripped) < 80:
                return True
        return False

    def _chunk_code(self, doc_id: str, text: str) -> List[Chunk]:
        lines = text.splitlines()
        total_lines = len(lines)
        if total_lines == 0:
            return []

        window = max(1, self.code_chunk_lines)
        overlap = max(0, min(self.code_overlap_lines, window - 1))
        step = max(1, window - overlap)

        # If the file is shorter than a single window, keep it whole
        if total_lines <= window:
            chunk_text = "\n".join(lines).strip()
            if not chunk_text:
                return []
            return [
                Chunk(
                    chunk_id=self._make_chunk_id(doc_id, 0),
                    text=chunk_text,
                    metadata={
                        "line_start": 1,
                        "line_end": total_lines,
                        "token_estimate": self._estimate_tokens(chunk_text),
                    },
                )
            ]

        chunks: List[Chunk] = []
        start = 0
        index = 0
        while start < total_lines:
            end = min(total_lines, start + window)
            chunk_lines = lines[start:end]
            chunk_text = "\n".join(chunk_lines).strip()
            if chunk_text:
                line_start = start + 1
                line_end = line_start + len(chunk_lines) - 1
                chunks.append(
                    Chunk(
                        chunk_id=self._make_chunk_id(doc_id, index),
                        text=chunk_text,
                        metadata={
                            "line_start": line_start,
                            "line_end": line_end,
                            "token_estimate": self._estimate_tokens(chunk_text),
                        },
                    )
                )
                index += 1
            if end >= total_lines:
                break
            start += step

        if not chunks:
            chunk_text = text.strip()
            if not chunk_text:
                return []
            return [
                Chunk(
                    chunk_id=self._make_chunk_id(doc_id, 0),
                    text=chunk_text,
                    metadata={
                        "line_start": 1,
                        "line_end": total_lines,
                        "token_estimate": self._estimate_tokens(chunk_text),
                    },
                )
            ]
        return chunks

    def _chunk_text(self, doc_id: str, text: str, category: str) -> List[Chunk]:
        normalized = re.sub(r"\n{3,}", "\n\n", text.strip())
        length = len(normalized)
        if length == 0:
            return []
        if length <= self.text_chunk_chars:
            return [
                Chunk(
                    chunk_id=self._make_chunk_id(doc_id, 0),
                    text=normalized,
                    metadata={
                        "char_start": 0,
                        "char_end": length,
                        "token_estimate": self._estimate_tokens(normalized),
                    },
                )
            ]

        chunks: List[Chunk] = []
        start = 0
        while start < length:
            target_end = min(length, start + self.text_chunk_chars)
            end = self._find_text_break(normalized, start, target_end)
            if end - start < max(self.min_index_chars, 200) and end < length:
                end = min(length, start + self.text_chunk_chars)
            # Guard against stalls
            if end <= start:
                end = min(length, start + self.text_chunk_chars)
                if end <= start:
                    end = length
            chunk_text = normalized[start:end].strip()
            if not chunk_text:
                if end <= start:
                    start += self.text_overlap_chars or 1
                else:
                    start = end
                continue
            chunk = Chunk(
                chunk_id=self._make_chunk_id(doc_id, len(chunks)),
                text=chunk_text,
                metadata={
                    "char_start": start,
                    "char_end": start + len(chunk_text),
                    "token_estimate": self._estimate_tokens(chunk_text),
                },
            )
            chunks.append(chunk)
            if end >= length:
                break
            start = max(0, end - self.text_overlap_chars)
        if not chunks:
            return [
                Chunk(
                    chunk_id=self._make_chunk_id(doc_id, 0),
                    text=normalized,
                    metadata={
                        "char_start": 0,
                        "char_end": length,
                        "token_estimate": self._estimate_tokens(normalized),
                    },
                )
            ]
        return chunks

    def _find_text_break(self, text: str, start: int, target_end: int) -> int:
        if target_end >= len(text):
            return len(text)
        window = text[start:target_end]
        # Prefer paragraph boundaries
        for pattern in ("\n\n", "\n"):
            idx = window.rfind(pattern)
            if idx != -1 and idx > 200:
                return start + idx
        # Try sentence boundaries
        sentence_match = re.search(r"[\.!?]\s+", text[target_end - 200 : target_end + 1])
        if sentence_match:
            pos = sentence_match.start() + target_end - 200
            if pos > start + 200:
                return pos
        # Look ahead slightly for a better boundary
        lookahead_end = min(len(text), target_end + self._text_boundary_lookahead)
        lookahead = text[target_end:lookahead_end]
        for pattern in ("\n\n", "\n"):
            idx = lookahead.find(pattern)
            if idx != -1:
                return target_end + idx
        sentence_ahead = re.search(r"[\.!?]\s+", lookahead)
        if sentence_ahead:
            return target_end + sentence_ahead.end()
        return target_end

    def _estimate_tokens(self, text: str) -> int:
        return max(1, len(text) // 4)

    def _make_chunk_id(self, doc_id: str, index: int) -> str:
        return f"{doc_id}#chunk-{index:04d}"
