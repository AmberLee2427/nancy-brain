"""Shared utility functions for nancy-brain scripts."""

import re
from typing import Optional


def is_full_commit_sha(ref: Optional[str]) -> bool:
    """Return True if *ref* is a full 40-character hexadecimal Git commit SHA."""
    return isinstance(ref, str) and bool(re.fullmatch(r"[0-9a-fA-F]{40}", ref))
