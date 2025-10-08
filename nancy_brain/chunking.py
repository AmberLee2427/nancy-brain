"""Compatibility helpers for chunk identifiers.

`SmartChunker` has been retired in favour of the external `chunky` package.
This module now only provides helpers that other components still import.
"""

from __future__ import annotations

from typing import Final

__all__ = ["strip_chunk_suffix"]

_CHUNK_MARKERS: Final[tuple[str, ...]] = ("#chunk-", "::chunk-", "|chunk:", "@chunk:")


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
