"""Tests for nancy_brain.pdf_ocr."""

import contextlib
import importlib.util
import json
import subprocess
import sys
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

    def fake_run(cmd, check=False, stdout=None, text=False, env=None, cwd=None):
        assert check is False
        assert stdout is subprocess.PIPE
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

    def fake_run(cmd, check=False, stdout=None, text=False, env=None, cwd=None):
        assert stdout is subprocess.PIPE
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

    def fake_run(cmd, check=False, stdout=None, text=False, env=None, cwd=None):
        assert stdout is subprocess.PIPE
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

    def fake_run(cmd, check=False, stdout=None, text=False, env=None, cwd=None):
        assert stdout is subprocess.PIPE
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


def test_warm_pdf_ocr_cache_batches_worker_invocation_for_multiple_pdfs(tmp_path):
    first_pdf = tmp_path / "first.pdf"
    second_pdf = tmp_path / "second.pdf"
    first_pdf.write_bytes(b"%PDF-first-worker-batch")
    second_pdf.write_bytes(b"%PDF-second-worker-batch")
    cache_dir = tmp_path / "cache"
    first_key = compute_pdf_content_hash(first_pdf)
    second_key = compute_pdf_content_hash(second_pdf)
    first_abs = first_pdf.resolve()
    second_abs = second_pdf.resolve()
    cache_dir_abs = cache_dir.resolve()

    def fake_run(cmd, check=False, stdout=None, text=False, env=None, cwd=None):
        assert check is False
        assert stdout is subprocess.PIPE
        assert text is True
        assert cmd[:3] == ["nancy-brain", "ocr", "worker"]
        assert cmd[3:5] == [str(first_abs), str(second_abs)]
        assert cmd[5:7] == ["--cache-dir", str(cache_dir_abs)]
        assert env is not None
        assert cwd == str(cache_dir_abs)
        assert env.get("NB_IN_OCR_WORKER") == "1"
        assert env.get("NB_OCR_WORKER_CMD") == ""

        for cache_key, title in ((first_key, "First"), (second_key, "Second")):
            cache_entry = cache_dir / cache_key
            cache_entry.mkdir(parents=True, exist_ok=True)
            (cache_entry / "content.md").write_text(f"# {title} Title\n\nBody.", encoding="utf-8")
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

        stdout = "\n".join(
            [
                json.dumps({"pdf_path": str(first_abs), "backend": "deepseek", "status": "generated"}),
                json.dumps({"pdf_path": str(second_abs), "backend": "deepseek", "status": "generated"}),
            ]
        )
        return subprocess.CompletedProcess(cmd, 0, stdout=stdout, stderr="")

    with (
        patch("nancy_brain.pdf_ocr._select_backend", return_value=None),
        patch("nancy_brain.pdf_ocr.subprocess.run", side_effect=fake_run) as mock_run,
    ):
        results = pdf_ocr.warm_pdf_ocr_cache([first_pdf, second_pdf], cache_dir=cache_dir, worker_cmd="nancy-brain")

    assert [result.status for result in results] == ["generated", "generated"]
    assert [result.markdown for result in results] == ["# First Title\n\nBody.", "# Second Title\n\nBody."]
    mock_run.assert_called_once()


def test_extract_pdf_markdown_logs_cache_write_progress(tmp_path, caplog):
    pdf_path = tmp_path / "paper.pdf"
    pdf_path.write_bytes(b"%PDF-log-test")
    cache_dir = tmp_path / "cache"
    fake_backend = FakeDeepSeekBackend()

    with (
        patch("nancy_brain.pdf_ocr._select_backend", return_value=fake_backend),
        patch("nancy_brain.pdf_ocr.render_pdf_to_images", return_value=[tmp_path / "page-0001.png"]),
        caplog.at_level("INFO", logger="nancy_brain.pdf_ocr"),
    ):
        result = extract_pdf_markdown(pdf_path, cache_dir=cache_dir)

    assert result.status == "generated"
    messages = [record.getMessage() for record in caplog.records]
    assert any("OCR start:" in message for message in messages)
    assert any("Rendered PDF pages:" in message for message in messages)
    assert any("Wrote OCR cache entry:" in message for message in messages)
    assert any("OCR complete:" in message for message in messages)


def test_deepseek_backend_strips_trailing_whitespace_from_prompt():
    backend = DeepSeekOCRBackend(prompt="<image>\n<|grounding|>Convert the document to markdown. ")

    assert backend.prompt == "<image>\n<|grounding|>Convert the document to markdown."


def test_deepseek_ocr_images_passes_eval_mode_true(tmp_path):
    backend = DeepSeekOCRBackend()
    backend._tokenizer = object()

    class FakeModel:
        def __init__(self):
            self.calls = []

        def infer(self, tokenizer, **kwargs):
            self.calls.append((tokenizer, kwargs))
            return "markdown output"

    fake_model = FakeModel()
    backend._model = fake_model

    fake_torch = types.SimpleNamespace(inference_mode=contextlib.nullcontext)
    with patch.dict(sys.modules, {"torch": fake_torch}):
        result = backend.ocr_images([tmp_path / "page-0001.png"])

    assert result == "## Page 1\n\nmarkdown output"
    assert len(fake_model.calls) == 1
    _, kwargs = fake_model.calls[0]
    assert kwargs["eval_mode"] is True
    assert kwargs["prompt"] == "<image>\n<|grounding|>Convert the document to markdown."


def test_deepseek_ocr_images_retries_without_eval_mode_when_unsupported(tmp_path):
    backend = DeepSeekOCRBackend()
    backend._tokenizer = object()

    class FakeModel:
        def __init__(self):
            self.calls = 0

        def infer(self, tokenizer, **kwargs):
            self.calls += 1
            if self.calls == 1:
                raise TypeError("infer() got an unexpected keyword argument 'eval_mode'")
            assert "eval_mode" not in kwargs
            return "markdown output"

    backend._model = FakeModel()

    fake_torch = types.SimpleNamespace(inference_mode=contextlib.nullcontext)
    with patch.dict(sys.modules, {"torch": fake_torch}):
        result = backend.ocr_images([tmp_path / "page-0001.png"])

    assert result == "## Page 1\n\nmarkdown output"


def test_default_pdf_ocr_cache_dir_prefers_cwd_project_root(tmp_path, monkeypatch):
    project_root = tmp_path / "Nancy"
    cache_dir = project_root / "knowledge_base" / "cache" / "pdf_ocr"
    cache_dir.mkdir(parents=True)
    monkeypatch.chdir(cache_dir)

    assert pdf_ocr.default_pdf_ocr_cache_dir() == cache_dir


def test_default_pdf_ocr_cache_dir_falls_back_to_cwd_not_site_packages(tmp_path, monkeypatch):
    working_dir = tmp_path / "random-working-dir"
    working_dir.mkdir()
    monkeypatch.chdir(working_dir)

    assert pdf_ocr.default_pdf_ocr_cache_dir() == working_dir / "knowledge_base" / "cache" / "pdf_ocr"


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


def test_resolve_deepseek_quantization_mode_auto_uses_4bit_for_small_gpu(monkeypatch):
    monkeypatch.delenv("NB_PDF_OCR_QUANTIZE", raising=False)
    monkeypatch.delenv("NB_QUANTIZE", raising=False)
    monkeypatch.delenv("NB_PDF_OCR_AUTO_4BIT_MAX_GIB", raising=False)
    monkeypatch.delenv("NB_PDF_OCR_AUTO_8BIT_MAX_GIB", raising=False)

    class FakeProps:
        total_memory = 12 * 1024**3

    class FakeCuda:
        @staticmethod
        def is_available():
            return True

        @staticmethod
        def current_device():
            return 0

        @staticmethod
        def get_device_properties(index):
            assert index == 0
            return FakeProps()

    class FakeTorch:
        cuda = FakeCuda()

    assert pdf_ocr._resolve_deepseek_quantization_mode(FakeTorch()) == "4bit"


def test_resolve_deepseek_quantization_mode_honors_explicit_override(monkeypatch):
    monkeypatch.setenv("NB_PDF_OCR_QUANTIZE", "8bit")

    class FakeCuda:
        @staticmethod
        def is_available():
            return True

    class FakeTorch:
        cuda = FakeCuda()

    assert pdf_ocr._resolve_deepseek_quantization_mode(FakeTorch()) == "8bit"


def test_deepseek_status_reports_missing_bitsandbytes_when_quantized(monkeypatch):
    backend = DeepSeekOCRBackend()

    class FakeCuda:
        @staticmethod
        def is_available():
            return True

        @staticmethod
        def current_device():
            return 0

        @staticmethod
        def get_device_properties(index):
            return types.SimpleNamespace(total_memory=12 * 1024**3)

    class FakeTorch:
        cuda = FakeCuda()

    monkeypatch.delenv("NB_PDF_OCR_QUANTIZE", raising=False)
    monkeypatch.delenv("NB_QUANTIZE", raising=False)

    original_find_spec = importlib.util.find_spec

    def fake_find_spec(name):
        if name == "bitsandbytes":
            return None
        return (
            object()
            if name in {"torchvision", "addict", "easydict", "einops", "matplotlib"}
            else original_find_spec(name)
        )

    monkeypatch.setattr("nancy_brain.pdf_ocr.find_spec", fake_find_spec)
    fake_transformers = types.ModuleType("transformers")
    fake_transformers.__version__ = "4.46.3"
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
    assert status.reason == "missing DeepSeek OCR quantization runtime dep: bitsandbytes (4bit)"


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
