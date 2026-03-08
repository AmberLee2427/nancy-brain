"""Tests for scripts/script_utils.py - shared utility functions."""

import pytest
from scripts.script_utils import is_full_commit_sha


def test_valid_full_sha_lowercase():
    sha = "a" * 40
    assert is_full_commit_sha(sha) is True


def test_valid_full_sha_uppercase():
    sha = "A" * 40
    assert is_full_commit_sha(sha) is True


def test_valid_full_sha_mixed():
    sha = "abc1234567890abcdef1234567890abcdef12345"
    assert len(sha) == 40
    assert is_full_commit_sha(sha) is True


def test_short_sha_returns_false():
    assert is_full_commit_sha("abc1234") is False


def test_tag_ref_returns_false():
    assert is_full_commit_sha("v1.0.0") is False


def test_branch_name_returns_false():
    assert is_full_commit_sha("main") is False


def test_none_returns_false():
    assert is_full_commit_sha(None) is False


def test_empty_string_returns_false():
    assert is_full_commit_sha("") is False


def test_non_hex_chars_returns_false():
    sha = "g" * 40  # 'g' is not a hex character
    assert is_full_commit_sha(sha) is False


def test_sha_with_spaces_returns_false():
    sha = "a" * 39 + " "
    assert is_full_commit_sha(sha) is False


def test_41_char_hex_returns_false():
    sha = "a" * 41
    assert is_full_commit_sha(sha) is False
