"""Tests for nancy_brain.pdf_ocr."""

import importlib.util
import json
import subprocess
import types
from pathlib import Path
from unittest.mock import patch

import nancy_brain.pdf_ocr as pdf_ocr
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
    assert first.status == "generated"
    assert second.cached is True
    assert second.status == "cached"
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
    assert result.status == "needs_ocr"
    assert result.needs_ocr is True
    assert result.deferred is True


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
    assert second.status == "cached"
    assert second.markdown == first.markdown


def test_extract_pdf_markdown_prefers_cache_over_worker_subprocess(tmp_path):
    pdf_path = tmp_path / "paper.pdf"
    pdf_path.write_bytes(b"%PDF-cache-first")
    cache_dir = tmp_path / "cache"
    fake_backend = FakeDeepSeekBackend()

    with (
        patch("nancy_brain.pdf_ocr._select_backend", return_value=fake_backend),
        patch("nancy_brain.pdf_ocr.render_pdf_to_images", return_value=[tmp_path / "page-0001.png"]),
    ):
        first = extract_pdf_markdown(pdf_path, cache_dir=cache_dir)

    with (
        patch("nancy_brain.pdf_ocr._select_backend", return_value=None),
        patch("nancy_brain.pdf_ocr.subprocess.run") as mock_run,
    ):
        second = extract_pdf_markdown(
            pdf_path,
            cache_dir=cache_dir,
            worker_cmd="nancy-brain",
        )

    assert first.cached is False
    assert second.cached is True
    assert second.status == "cached"
    assert second.markdown == first.markdown
    mock_run.assert_not_called()


def test_extract_pdf_markdown_invokes_worker_subprocess_on_cache_miss(tmp_path):
    pdf_path = tmp_path / "paper.pdf"
    pdf_path.write_bytes(b"%PDF-worker-generate")
    cache_dir = tmp_path / "cache"
    cache_key = compute_pdf_content_hash(pdf_path)
    pdf_path_abs = pdf_path.resolve()
    cache_dir_abs = cache_dir.resolve()

    def fake_run(cmd, check=False, capture_output=False, text=False, env=None, cwd=None):
        assert check is False
        assert capture_output is True
        assert text is True
        assert cmd[:3] == ["nancy-brain", "ocr", "worker"]
        assert cmd[3] == str(pdf_path_abs)
        assert cmd[4:6] == ["--cache-dir", str(cache_dir_abs)]
        assert env is not None
        assert cwd == str(cache_dir_abs)
        assert env.get("NB_IN_OCR_WORKER") == "1"
        assert env.get("NB_OCR_WORKER_CMD") == ""
        cache_entry = cache_dir / cache_key
        cache_entry.mkdir(parents=True, exist_ok=True)
        (cache_entry / "content.md").write_text("# Worker Title\n\nWorker body.", encoding="utf-8")
        (cache_entry / "metadata.json").write_text(
            json.dumps(
                {
                    "pdf_sha256": cache_key,
                    "backend": "deepseek",
                    "status": "generated",
                    "model": "deepseek-ai/DeepSeek-OCR",
                    "page_count": 2,
                    "signature": {"cache_version": 1},
                }
            ),
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(
            cmd, 0, stdout=json.dumps({"backend": "deepseek", "status": "generated"}), stderr=""
        )

    with (
        patch("nancy_brain.pdf_ocr._select_backend", return_value=None),
        patch("nancy_brain.pdf_ocr.subprocess.run", side_effect=fake_run) as mock_run,
    ):
        result = extract_pdf_markdown(pdf_path, cache_dir=cache_dir, worker_cmd="nancy-brain")

    assert result.cached is False
    assert result.status == "generated"
    assert result.markdown == "# Worker Title\n\nWorker body."
    assert result.backend == "deepseek"
    assert result.page_count == 2
    mock_run.assert_called_once()


def test_extract_pdf_markdown_uses_worker_command_from_environment(tmp_path, monkeypatch):
    pdf_path = tmp_path / "paper.pdf"
    pdf_path.write_bytes(b"%PDF-worker-env")
    cache_dir = tmp_path / "cache"
    cache_key = compute_pdf_content_hash(pdf_path)
    pdf_path_abs = pdf_path.resolve()
    cache_dir_abs = cache_dir.resolve()

    monkeypatch.setenv("NB_OCR_WORKER_CMD", "python -m nancy_brain.cli ocr worker")

    def fake_run(cmd, check=False, capture_output=False, text=False, env=None, cwd=None):
        assert cmd[:3] == ["python", "-m", "nancy_brain.cli"]
        assert cmd[3:5] == ["ocr", "worker"]
        assert cmd[5] == str(pdf_path_abs)
        assert env is not None
        assert cmd[6:8] == ["--cache-dir", str(cache_dir_abs)]
        assert cwd == str(cache_dir_abs)
        assert env.get("NB_IN_OCR_WORKER") == "1"
        assert env.get("NB_OCR_WORKER_CMD") == ""
        cache_entry = cache_dir / cache_key
        cache_entry.mkdir(parents=True, exist_ok=True)
        (cache_entry / "content.md").write_text("# Env Title\n\nEnv body.", encoding="utf-8")
        (cache_entry / "metadata.json").write_text(
            json.dumps(
                {
                    "pdf_sha256": cache_key,
                    "backend": "deepseek",
                    "status": "generated",
                    "model": "deepseek-ai/DeepSeek-OCR",
                    "page_count": 1,
                    "signature": {"cache_version": 1},
                }
            ),
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(
            cmd, 0, stdout=json.dumps({"backend": "deepseek", "status": "generated"}), stderr=""
        )

    with (
        patch("nancy_brain.pdf_ocr._select_backend", return_value=None),
        patch("nancy_brain.pdf_ocr.subprocess.run", side_effect=fake_run) as mock_run,
    ):
        result = extract_pdf_markdown(pdf_path, cache_dir=cache_dir)

    assert result.status == "generated"
    assert result.markdown == "# Env Title\n\nEnv body."
    mock_run.assert_called_once()


def test_resolve_worker_command_prefers_explicit_command_over_environment(monkeypatch):
    monkeypatch.setenv("NB_OCR_WORKER_CMD", "env-nancy ocr worker")

    command = pdf_ocr._resolve_worker_command(["explicit-nancy", "ocr", "worker"])

    assert command == ["explicit-nancy"]


def test_resolve_worker_command_uses_project_config_before_shared_path(tmp_path, monkeypatch):
    project_root = tmp_path / "project"
    nested_root = project_root / "subdir" / "deep"
    nested_root.mkdir(parents=True)
    (project_root / "config").mkdir()
    (project_root / "config" / "ocr_worker.toml").write_text(
        'worker_cmd = "project-nancy ocr worker"\n', encoding="utf-8"
    )
    monkeypatch.chdir(nested_root)
    monkeypatch.delenv("NB_OCR_WORKER_CMD", raising=False)
    monkeypatch.setattr(
        pdf_ocr,
        "_default_shared_worker_command",
        lambda: (_ for _ in ()).throw(AssertionError("shared path should not be used")),
    )

    command = pdf_ocr._resolve_worker_command()

    assert command == ["project-nancy"]


def test_extract_pdf_markdown_reports_malformed_project_worker_config(tmp_path, monkeypatch):
    project_root = tmp_path / "project"
    pdf_path = project_root / "papers" / "paper.pdf"
    config_path = project_root / "config" / "ocr_worker.toml"
    outside_root = tmp_path / "outside"
    pdf_path.parent.mkdir(parents=True)
    config_path.parent.mkdir(parents=True)
    outside_root.mkdir()
    project_root.joinpath("pyproject.toml").write_text("[project]\nname = 'demo'\n", encoding="utf-8")
    pdf_path.write_bytes(b"%PDF-config-error")
    config_path.write_text("worker_cmd = \n", encoding="utf-8")
    monkeypatch.chdir(outside_root)

    with (
        patch("nancy_brain.pdf_ocr._select_backend", return_value=None),
        patch("nancy_brain.pdf_ocr.subprocess.run") as mock_run,
    ):
        result = extract_pdf_markdown(pdf_path, cache_dir=tmp_path / "cache")

    assert result.status == "error"
    assert result.markdown is None
    assert "OCR worker config" in (result.warning or "")
    mock_run.assert_not_called()


def test_extract_pdf_markdown_reports_missing_project_worker_command(tmp_path, monkeypatch):
    project_root = tmp_path / "project"
    pdf_path = project_root / "papers" / "paper.pdf"
    config_path = project_root / "config" / "ocr_worker.toml"
    pdf_path.parent.mkdir(parents=True)
    config_path.parent.mkdir(parents=True)
    project_root.joinpath("pyproject.toml").write_text("[project]\nname = 'demo'\n", encoding="utf-8")
    pdf_path.write_bytes(b"%PDF-config-missing")
    config_path.write_text("[worker]\nname = 'ocr'\n", encoding="utf-8")

    with (
        patch("nancy_brain.pdf_ocr._select_backend", return_value=None),
        patch("nancy_brain.pdf_ocr.subprocess.run") as mock_run,
    ):
        result = extract_pdf_markdown(pdf_path, cache_dir=tmp_path / "cache")

    assert result.status == "error"
    assert result.markdown is None
    assert "does not define worker_cmd" in (result.warning or "")
    mock_run.assert_not_called()


def test_extract_pdf_markdown_finds_project_worker_config_outside_cwd(tmp_path, monkeypatch):
    project_root = tmp_path / "project"
    pdf_path = project_root / "papers" / "paper.pdf"
    config_path = project_root / "config" / "ocr_worker.toml"
    outside_root = tmp_path / "outside"
    outside_config = outside_root / "config" / "ocr_worker.toml"
    pdf_path.parent.mkdir(parents=True)
    config_path.parent.mkdir(parents=True)
    outside_config.parent.mkdir(parents=True)
    project_root.joinpath("pyproject.toml").write_text("[project]\nname = 'demo'\n", encoding="utf-8")
    pdf_path.write_bytes(b"%PDF-outside-cwd")
    config_path.write_text('worker_cmd = "project-nancy ocr worker"\n', encoding="utf-8")
    outside_config.write_text('worker_cmd = "outside-nancy ocr worker"\n', encoding="utf-8")
    monkeypatch.chdir(outside_root)
    cache_dir = tmp_path / "cache"
    cache_key = compute_pdf_content_hash(pdf_path)
    pdf_path_abs = pdf_path.resolve()
    cache_dir_abs = cache_dir.resolve()

    def fake_run(cmd, check=False, capture_output=False, text=False, env=None, cwd=None):
        assert cmd[:3] == ["project-nancy", "ocr", "worker"]
        assert cmd[3] == str(pdf_path_abs)
        assert cmd[4:6] == ["--cache-dir", str(cache_dir_abs)]
        assert cwd == str(cache_dir_abs)
        cache_entry = cache_dir / cache_key
        cache_entry.mkdir(parents=True, exist_ok=True)
        (cache_entry / "content.md").write_text("# Project Title\n\nBody.", encoding="utf-8")
        (cache_entry / "metadata.json").write_text(
            json.dumps(
                {
                    "pdf_sha256": cache_key,
                    "backend": "deepseek",
                    "status": "generated",
                    "model": "deepseek-ai/DeepSeek-OCR",
                    "page_count": 1,
                    "signature": {"cache_version": 1},
                }
            ),
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(
            cmd, 0, stdout=json.dumps({"backend": "deepseek", "status": "generated"}), stderr=""
        )

    with (
        patch("nancy_brain.pdf_ocr._select_backend", return_value=None),
        patch("nancy_brain.pdf_ocr.subprocess.run", side_effect=fake_run) as mock_run,
    ):
        result = extract_pdf_markdown(pdf_path, cache_dir=cache_dir)

    assert result.status == "generated"
    assert result.markdown == "# Project Title\n\nBody."
    mock_run.assert_called_once()


def test_extract_pdf_markdown_passes_absolute_paths_to_worker_when_called_from_project_cwd(tmp_path, monkeypatch):
    project_root = tmp_path / "project"
    pdf_path = project_root / "knowledge_base" / "raw" / "journal_articles" / "paper.pdf"
    cache_dir = project_root / "knowledge_base" / "cache" / "pdf_ocr"
    pdf_path.parent.mkdir(parents=True)
    pdf_path.write_bytes(b"%PDF-relative-worker")
    monkeypatch.chdir(project_root)

    def fake_run(cmd, check=False, capture_output=False, text=False, env=None, cwd=None):
        assert cmd[:3] == ["nancy-brain", "ocr", "worker"]
        assert cmd[3] == str(pdf_path.resolve())
        assert cmd[4:6] == ["--cache-dir", str(cache_dir.resolve())]
        assert cwd == str(cache_dir.resolve())
        return subprocess.CompletedProcess(
            cmd,
            1,
            stdout=json.dumps({"warning": "worker boom"}),
            stderr="",
        )

    with (
        patch("nancy_brain.pdf_ocr._select_backend", return_value=None),
        patch("nancy_brain.pdf_ocr.subprocess.run", side_effect=fake_run) as mock_run,
    ):
        result = extract_pdf_markdown(pdf_path.relative_to(project_root), cache_dir=cache_dir, worker_cmd="nancy-brain")

    assert result.status == "error"
    assert result.warning == "worker boom"
    mock_run.assert_called_once()


def test_resolve_worker_command_uses_shared_worker_path_when_config_missing(monkeypatch):
    monkeypatch.delenv("NB_OCR_WORKER_CMD", raising=False)
    monkeypatch.setattr(pdf_ocr, "_load_worker_command_from_project_config", lambda *args, **kwargs: (None, None))
    monkeypatch.setattr(
        pdf_ocr, "_default_shared_worker_command", lambda: ["/opt/nancy-brain/ocr-worker/bin/nancy-brain"]
    )

    command = pdf_ocr._resolve_worker_command()

    assert command == ["/opt/nancy-brain/ocr-worker/bin/nancy-brain"]


def test_resolve_worker_command_returns_none_when_no_sources(monkeypatch):
    monkeypatch.delenv("NB_OCR_WORKER_CMD", raising=False)
    monkeypatch.setenv("NB_IN_OCR_WORKER", "")
    monkeypatch.setattr(pdf_ocr, "_load_worker_command_from_project_config", lambda *args, **kwargs: (None, None))
    monkeypatch.setattr(pdf_ocr, "_default_shared_worker_command", lambda: None)

    command = pdf_ocr._resolve_worker_command()

    assert command is None


def test_default_shared_worker_command_prefers_localappdata_on_windows(tmp_path, monkeypatch):
    shared_root = tmp_path / "LocalAppData" / "nancy-brain" / "ocr-worker"
    worker_bin = shared_root / "Scripts" / "nancy-brain.exe"
    worker_bin.parent.mkdir(parents=True)
    worker_bin.write_text("echo worker\n", encoding="utf-8")
    worker_bin.chmod(0o755)

    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "LocalAppData"))
    monkeypatch.setattr(pdf_ocr.os, "name", "nt", raising=False)
    monkeypatch.setattr(pdf_ocr, "_windows_shared_worker_base", lambda: shared_root)

    command = pdf_ocr._default_shared_worker_command()

    assert command == [str(worker_bin)]


def test_extract_pdf_markdown_worker_env_guard_disables_spawn(tmp_path, monkeypatch):
    pdf_path = tmp_path / "paper.pdf"
    pdf_path.write_bytes(b"%PDF-worker-guard")
    cache_dir = tmp_path / "cache"

    monkeypatch.setenv("NB_OCR_WORKER_CMD", "python -m nancy_brain.cli ocr worker")
    monkeypatch.setenv("NB_IN_OCR_WORKER", "1")

    with (
        patch("nancy_brain.pdf_ocr._select_backend", return_value=None),
        patch("nancy_brain.pdf_ocr.subprocess.run") as mock_run,
    ):
        result = extract_pdf_markdown(pdf_path, cache_dir=cache_dir)

    assert result.status == "needs_ocr"
    assert result.needs_ocr is True
    mock_run.assert_not_called()


def test_extract_pdf_markdown_worker_failure_returns_error(tmp_path):
    pdf_path = tmp_path / "paper.pdf"
    pdf_path.write_bytes(b"%PDF-worker-failure")
    cache_dir = tmp_path / "cache"

    with (
        patch("nancy_brain.pdf_ocr._select_backend", return_value=None),
        patch(
            "nancy_brain.pdf_ocr.subprocess.run",
            return_value=subprocess.CompletedProcess(
                ["nancy-brain", "ocr", "worker", str(pdf_path)],
                1,
                stdout=json.dumps({"warning": "worker boom"}),
                stderr="",
            ),
        ),
    ):
        result = extract_pdf_markdown(pdf_path, cache_dir=cache_dir, worker_cmd="nancy-brain")

    assert result.status == "error"
    assert result.markdown is None
    assert result.warning == "worker boom"


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
