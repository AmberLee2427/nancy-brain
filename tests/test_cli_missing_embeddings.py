import subprocess
import sys
from pathlib import Path

import pytest


def test_search_missing_embeddings_message(tmp_path, capsys):
    """Running the CLI search when embeddings are missing prints a helpful tip."""
    # Run the CLI search command pointing at a temp embeddings path with no index
    env = dict(**{})
    cmd = [
        sys.executable,
        "-m",
        "nancy_brain.cli",
        "search",
        "dummy-query",
        "--embeddings-path",
        str(tmp_path / "emb"),
    ]  # noqa: E501
    result = subprocess.run(cmd, capture_output=True, env=env)
    out = result.stdout.decode("utf-8") + result.stderr.decode("utf-8")
    assert "Embeddings index missing" in out
    assert "nancy-brain build" in out
