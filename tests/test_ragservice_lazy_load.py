import sys
from pathlib import Path

import pytest

from rag_core.service import RAGService


def test_ragservice_lazy_without_txtai(tmp_path, monkeypatch):
    """RAGService should not raise when txtai isn't available; search should be None."""
    # Ensure rag_core.search cannot be imported (simulate missing txtai)
    monkeypatch.setitem(sys.modules, "rag_core.search", None)

    embeddings_path = tmp_path / "emb"
    embeddings_path.mkdir()
    # No index dir present -> service should not attempt to load search
    # Provide a minimal config file path to avoid Registry errors during tests
    cfg_file = tmp_path / "repositories.yml"
    cfg_file.write_text("{}")
    svc = RAGService(
        embeddings_path=embeddings_path,
        config_path=cfg_file,
        weights_path=Path("/nope/weights.yml"),
    )

    # Accessing a method that uses search should behave gracefully and not raise
    assert svc.search is None
    ctx = svc.get_context_for_query("anything")
    assert isinstance(ctx, str)
    assert "No relevant information" in ctx or ctx == "No relevant information found."


def test_ragservice_lazy_with_mocked_search(tmp_path, monkeypatch):
    """If a Search implementation exists (mocked), RAGService should initialize it lazily."""

    # Create a tiny fake Search class in a dummy module and inject into sys.modules
    import types

    fake_search_mod = types.ModuleType("rag_core.search")

    class FakeSearch:
        def __init__(self, embeddings_path, dual=False, code_model=None):
            self.embeddings_path = embeddings_path
            self.general_embeddings = True

        def search(self, query, limit):
            return [{"id": "a/b.txt", "text": "hello world", "score": 0.9}]

    fake_search_mod.Search = FakeSearch

    monkeypatch.setitem(sys.modules, "rag_core.search", fake_search_mod)

    embeddings_path = tmp_path / "emb"
    embeddings_path.mkdir()
    (embeddings_path / "index").mkdir()

    svc = RAGService(
        embeddings_path=embeddings_path,
        config_path=Path("/nope/config.yml"),
        weights_path=Path("/nope/weights.yml"),
    )

    # Before any call, search should be None (lazy)
    assert svc.search is None

    # Call the async search_docs via asyncio.run to exercise lazy load
    import asyncio

    async def runner():
        res = await svc.search_docs("q", limit=1)
        return res

    got = asyncio.run(runner())
    assert isinstance(got, list)
    assert len(got) == 1
    assert got[0]["id"] == "a/b.txt"
