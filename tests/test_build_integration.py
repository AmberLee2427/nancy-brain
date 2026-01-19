import os
import shutil
from pathlib import Path
import tempfile
import yaml

from scripts.build_knowledge_base import build_txtai_index


class DummyEmbeddings:
    instances = []

    def __init__(self, *args, **kwargs):
        self.indexed = []
        DummyEmbeddings.instances.append(self)

    def index(self, docs):
        # docs is an iterable of (id, text, metadata)
        self.indexed.extend(list(docs))

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
    assert DummyEmbeddings.instances
    indexed_docs = DummyEmbeddings.instances[0].indexed
    assert indexed_docs, "expected indexed documents"
    # Ensure metadata is preserved for chunked documents
    for doc in indexed_docs:
        assert len(doc) == 3
        _, _, metadata = doc
        assert "source_document" in metadata


class StubSummaryResult:
    def __init__(self, doc_id, readme_path=None):
        self.summary = f"Summary for {doc_id}"
        self.weight = 1.4
        self.model = "test-model"
        self.cached = False
        self.repo_readme_path = readme_path


class StubSummaryGenerator:
    def __init__(self):
        self.calls = []
        self.readme_paths = []

    def summarize(
        self,
        *,
        doc_id,
        content,
        repo_name=None,
        repo_readme=None,
        repo_readme_path=None,
        repo_description=None,
        metadata=None,
    ):
        self.calls.append(doc_id)
        self.readme_paths.append(repo_readme_path)
        return StubSummaryResult(doc_id, repo_readme_path)


def test_build_txtai_index_with_summaries(tmp_path, monkeypatch):
    base = tmp_path / "knowledge_base" / "raw"
    repo_dir = base / "docs" / "repo"
    repo_dir.mkdir(parents=True)
    (repo_dir / "README.md").write_text("Repo overview", encoding="utf-8")
    (repo_dir / "file.md").write_text("# Header\n\nSome detailed content.", encoding="utf-8")

    repos_config = {"docs": [{"name": "repo", "url": "https://example.com/repo"}]}
    config_path = tmp_path / "repos.yml"
    with open(config_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(repos_config, f)

    monkeypatch.setitem(__import__("builtins").__dict__, "Embeddings", DummyEmbeddings)
    import sys

    class DummyModule:
        Embeddings = DummyEmbeddings

    prev = sys.modules.get("txtai.embeddings")
    try:
        sys.modules["txtai.embeddings"] = DummyModule()

        summary_generator = StubSummaryGenerator()
        failures = build_txtai_index(
            str(config_path),
            articles_config_path=None,
            base_path=str(base),
            embeddings_path=str(tmp_path / "embeddings"),
            dry_run=False,
            category="docs",
            summary_generator=summary_generator,
        )
    finally:
        if prev is not None:
            sys.modules["txtai.embeddings"] = prev
        else:
            sys.modules.pop("txtai.embeddings", None)

    assert summary_generator.calls
    assert "auto_model_weights" in failures
    indexed_docs = DummyEmbeddings.instances[-1].indexed
    summary_ids = [doc[0] for doc in indexed_docs if doc[0].startswith("summaries/")]
    assert summary_ids, "expected summary documents to be indexed"
    summary_metadata = [meta for doc_id, _, meta in indexed_docs if doc_id.startswith("summaries/")]
    assert any("repo_readme_path" in meta for meta in summary_metadata)
    assert "README.md" in summary_generator.readme_paths
