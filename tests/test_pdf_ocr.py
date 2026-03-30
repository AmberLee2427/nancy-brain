"""Tests for nancy_brain.pdf_ocr."""

import importlib.util
import types
from pathlib import Path
from unittest.mock import patch

from nancy_brain.pdf_ocr import (
    PDFOCRBackendStatus,
    DeepSeekOCRBackend,
    compute_pdf_content_hash,
    extract_pdf_markdown,
)


class FakeDeepSeekBackend:
    """Small fake backend used to exercise cache behavior deterministically."""

    name = "deepseek"
    model_name = "deepseek-ai/DeepSeek-OCR"
    render_scale = 2.0

    def __init__(self) -> None:
        self.calls = 0

    def signature(self) -> dict:
        return {
            "backend": self.name,
            "model": self.model_name,
            "prompt": "<image>\n<|grounding|>Convert the document to markdown.",
            "render_scale": self.render_scale,
            "base_size": 1024,
            "image_size": 640,
            "crop_mode": True,
            "cache_version": 1,
        }

    def ocr_images(self, image_paths: list[Path]) -> str:
        self.calls += 1
        assert image_paths
        return "## Page 1\n\n# Extracted Title\n\nExtracted body text."


def test_compute_pdf_content_hash_changes_with_content(tmp_path):
    first = tmp_path / "first.pdf"
    second = tmp_path / "second.pdf"
    first.write_bytes(b"%PDF-one")
    second.write_bytes(b"%PDF-two")

    assert compute_pdf_content_hash(first) != compute_pdf_content_hash(second)


def test_extract_pdf_markdown_caches_by_content_hash(tmp_path):
    pdf_path = tmp_path / "paper.pdf"
    pdf_path.write_bytes(b"%PDF-cache-test")
    cache_dir = tmp_path / "cache"
    fake_backend = FakeDeepSeekBackend()

    with (
        patch("nancy_brain.pdf_ocr._select_backend", return_value=fake_backend),
        patch("nancy_brain.pdf_ocr.render_pdf_to_images", return_value=[tmp_path / "page-0001.png"]),
    ):
        first = extract_pdf_markdown(pdf_path, cache_dir=cache_dir)
        second = extract_pdf_markdown(pdf_path, cache_dir=cache_dir)

    assert first.cached is False
    assert second.cached is True
    assert second.markdown == first.markdown
    assert second.cache_key == first.cache_key
    assert fake_backend.calls == 1
    assert (cache_dir / first.cache_key / "content.md").exists()
    assert (cache_dir / first.cache_key / "metadata.json").exists()


def test_extract_pdf_markdown_returns_warning_without_backend(tmp_path):
    pdf_path = tmp_path / "paper.pdf"
    pdf_path.write_bytes(b"%PDF-no-backend")
    status = PDFOCRBackendStatus(name="none", available=False, reason="CUDA unavailable")

    with (
        patch("nancy_brain.pdf_ocr._select_backend", return_value=None),
        patch("nancy_brain.pdf_ocr.get_pdf_ocr_backend_status", return_value=status),
    ):
        result = extract_pdf_markdown(pdf_path, cache_dir=tmp_path / "cache")

    assert result.markdown is None
    assert result.warning == "CUDA unavailable"
    assert result.backend == "none"


def test_extract_pdf_markdown_uses_cache_without_live_backend(tmp_path):
    pdf_path = tmp_path / "paper.pdf"
    pdf_path.write_bytes(b"%PDF-cache-reuse")
    cache_dir = tmp_path / "cache"
    fake_backend = FakeDeepSeekBackend()

    with (
        patch("nancy_brain.pdf_ocr._select_backend", return_value=fake_backend),
        patch("nancy_brain.pdf_ocr.render_pdf_to_images", return_value=[tmp_path / "page-0001.png"]),
    ):
        first = extract_pdf_markdown(pdf_path, cache_dir=cache_dir)

    status = PDFOCRBackendStatus(name="none", available=False, reason="CUDA unavailable")
    with (
        patch("nancy_brain.pdf_ocr._select_backend", return_value=None),
        patch("nancy_brain.pdf_ocr.get_pdf_ocr_backend_status", return_value=status),
    ):
        second = extract_pdf_markdown(pdf_path, cache_dir=cache_dir)

    assert first.cached is False
    assert second.cached is True
    assert second.markdown == first.markdown


def test_deepseek_status_reports_missing_runtime_dependencies(monkeypatch):
    backend = DeepSeekOCRBackend()

    class FakeCuda:
        @staticmethod
        def is_available():
            return True

    class FakeTorch:
        cuda = FakeCuda()

    original_find_spec = importlib.util.find_spec

    def fake_find_spec(name):
        if name == "torchvision":
            return None
        return original_find_spec(name)

    monkeypatch.setattr("nancy_brain.pdf_ocr.find_spec", fake_find_spec)
    fake_transformers = types.ModuleType("transformers")
    fake_transformers.__path__ = []
    fake_transformers.AutoModel = object()
    fake_transformers.AutoTokenizer = object()
    fake_transformers_models = types.ModuleType("transformers.models")
    fake_transformers_models.__path__ = []
    fake_transformers_llama = types.ModuleType("transformers.models.llama")
    fake_transformers_llama.__path__ = []
    fake_transformers_llama_modeling = types.ModuleType("transformers.models.llama.modeling_llama")
    fake_transformers_llama_modeling.LlamaFlashAttention2 = object()
    with patch.dict(
        "sys.modules",
        {
            "torch": FakeTorch(),
            "transformers": fake_transformers,
            "transformers.models": fake_transformers_models,
            "transformers.models.llama": fake_transformers_llama,
            "transformers.models.llama.modeling_llama": fake_transformers_llama_modeling,
        },
    ):
        status = backend.status()

    assert status.available is False
    assert status.reason is not None
    assert status.reason.startswith("missing DeepSeek OCR runtime deps: ")
    assert "torchvision" in status.reason


def test_deepseek_status_reports_transformers_incompatibility(monkeypatch):
    backend = DeepSeekOCRBackend()

    class FakeCuda:
        @staticmethod
        def is_available():
            return True

    class FakeTorch:
        cuda = FakeCuda()

    fake_transformers = types.ModuleType("transformers")
    fake_transformers.__version__ = "5.3.0"
    fake_transformers.AutoModel = object()
    fake_transformers.AutoTokenizer = object()

    original_import = __import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "tokenizers":
            fake_tokenizers = types.ModuleType("tokenizers")
            fake_tokenizers.__version__ = "0.22.0"
            return fake_tokenizers
        if name == "transformers.models.llama.modeling_llama":
            raise ImportError("cannot import name 'LlamaFlashAttention2'")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr("nancy_brain.pdf_ocr.find_spec", lambda name: object())
    with (
        patch.dict("sys.modules", {"torch": FakeTorch(), "transformers": fake_transformers}),
        patch("builtins.__import__", side_effect=fake_import),
    ):
        status = backend.status()

    assert status.available is False
    assert status.reason is not None
    assert "incompatible transformers stack for DeepSeek OCR" in status.reason
    assert "transformers 5.3.0" in status.reason
    assert "tokenizers 0.22.0" in status.reason
