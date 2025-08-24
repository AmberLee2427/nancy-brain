import os

os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

import asyncio
from pathlib import Path
import pytest
from unittest.mock import patch

from rag_core.search import Search
from rag_core.service import RAGService


class FakeEmbeddings:
    def __init__(self, results):
        self._results = results

    def search(self, query, limit):
        # ignore query, limit, just return preset
        return self._results


@pytest.mark.asyncio
async def test_search_extension_and_model_weights(tmp_path):
    """Search._process_and_rank_results applies extension + model weights correctly."""
    # Prevent actual embedding loading
    with patch.object(Search, "_load_embeddings", return_value=None):
        # Config extension weights
        ext_cfg = {"extensions": {".py": 0.9, ".md": 0.98}}
        model_weights = {"file1.py": 2.0, "docs/readme.md": 0.5}
        s = Search(
            tmp_path / "emb",
            dual=False,
            extension_weights=ext_cfg,
            model_weights=model_weights,
        )
        # Inject fake embeddings returning base scores
        s.general_embeddings = FakeEmbeddings(
            [
                {"id": "file1.py", "text": "code file", "score": 1.0},
                {"id": "docs/readme.md", "text": "readme file", "score": 1.0},
            ]
        )
        results = s.search("query", limit=2)
        # Expect order: file1.py first due to higher adjusted score
        assert results[0]["id"] == "file1.py"
        # Extract adjusted scores
        adj = {r["id"]: r["adjusted_score"] for r in results}
        # file1: 0.9 * 2.0 * 1.0 = 1.8
        # readme: 0.98 * 0.5 * 1.0 = 0.49
        assert pytest.approx(adj["file1.py"], rel=1e-6) == 1.8
        assert pytest.approx(adj["docs/readme.md"], rel=1e-6) == 0.49


@pytest.mark.asyncio
async def test_runtime_weight_updates_results(tmp_path):
    """RAGService.set_weight immediately influences adjusted_score in subsequent searches."""
    embeddings_path = tmp_path / "emb"
    embeddings_path.mkdir()
    weights_path = tmp_path / "weights.yaml"
    weights_path.write_text("extensions: {}")
    config_path = tmp_path / "repositories.yml"
    config_path.write_text("{}")

    # Patch embedding load in both Search and Registry usage
    with patch.object(Search, "_load_embeddings", return_value=None):
        rag = RAGService(
            embeddings_path=embeddings_path,
            config_path=config_path,
            weights_path=weights_path,
            use_dual_embedding=False,
        )
        # Provide fake embeddings
        rag.search.general_embeddings = FakeEmbeddings([{"id": "foo.py", "text": "foo code", "score": 1.0}])
        # First search (no weight)
        first = await rag.search_docs("x", limit=1)
        assert first[0]["id"] == "foo.py"
        base_adjusted = first[0]["adjusted_score"]
        assert pytest.approx(base_adjusted, rel=1e-6) == 1.0  # default adjusted = 1
        # Set weight
        await rag.set_weight("foo.py", 2.0)
        # Second search
        second = await rag.search_docs("x", limit=1)
        assert second[0]["id"] == "foo.py"
        new_adjusted = second[0]["adjusted_score"]
        # Expect doubling (extension weight default 1.0)
        assert pytest.approx(new_adjusted, rel=1e-6) == 2.0
        # Model score field should reflect updated multiplier (clamped logic inside search not applied to adjusted_score beyond 0.5-2.0 range)
        assert second[0]["model_score"] == 2.0
