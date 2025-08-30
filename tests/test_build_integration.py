import os
import shutil
from pathlib import Path
import tempfile
import yaml

from scripts.build_knowledge_base import build_txtai_index


class DummyEmbeddings:
    def __init__(self, *args, **kwargs):
        self.indexed = []

    def index(self, docs):
        # docs is an iterable of (id, text)
        self.indexed.extend(docs)

    def save(self, path):
        Path(path).mkdir(parents=True, exist_ok=True)

    def search(self, q, n):
        return []


def test_build_txtai_index_processes_text_files(tmp_path, monkeypatch):
    # Create a fake repo structure
    base = tmp_path / "knowledge_base" / "raw"
    repo_dir = base / "docs" / "sample_repo"
    repo_dir.mkdir(parents=True)
    # Create sample files
    (repo_dir / "a.txt").write_text("Hello world from txt", encoding="utf-8")
    (repo_dir / "b.rst").write_text("Title\n=====\n\nThis is rst content.", encoding="utf-8")
    (repo_dir / "c.tex").write_text("\\section{Intro}\\nThis is latex content.", encoding="utf-8")

    # Write a minimal repositories config that points to our sample repo folder
    repos_config = {"docs": [{"name": "sample_repo", "url": "https://example.local/sample_repo"}]}
    config_path = tmp_path / "repos.yml"
    with open(config_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(repos_config, f)

    # Monkeypatch Embeddings to avoid loading models
    monkeypatch.setitem(__import__("builtins").__dict__, "Embeddings", DummyEmbeddings)

    # Also patch the import inside build_txtai_index by placing DummyEmbeddings in the txtai.embeddings namespace
    import sys

    class DummyModule:
        Embeddings = DummyEmbeddings

    # Insert dummy module but ensure we restore any existing module after the test
    prev = sys.modules.get("txtai.embeddings")
    try:
        sys.modules["txtai.embeddings"] = DummyModule()

        failures = build_txtai_index(
            str(config_path),
            articles_config_path=None,
            base_path=str(base),
            embeddings_path=str(tmp_path / "embeddings"),
            dry_run=False,
            category="docs",
        )
    finally:
        # Restore previous module (or remove our dummy) to avoid side effects
        if prev is not None:
            sys.modules["txtai.embeddings"] = prev
        else:
            sys.modules.pop("txtai.embeddings", None)

    assert failures["successful_text_files"] >= 3
