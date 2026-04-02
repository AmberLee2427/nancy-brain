"""Tests for managed OCR worker runtime helpers."""

import json
import subprocess
from pathlib import Path

from nancy_brain.ocr_worker_runtime import (
    install_local_ocr_worker,
    verify_local_ocr_worker,
    worker_launcher_command,
)


def test_install_local_ocr_worker_writes_launcher_and_metadata(tmp_path, monkeypatch):
    commands: list[list[str]] = []

    def fake_run(cmd, check=False, capture_output=False, text=False, env=None):
        commands.append([str(part) for part in cmd])
        if len(cmd) >= 4 and str(cmd[1]) == "-m" and str(cmd[2]) == "venv":
            venv_dir = Path(cmd[3])
            python_path = venv_dir / "bin" / "python"
            python_path.parent.mkdir(parents=True, exist_ok=True)
            python_path.write_text("", encoding="utf-8")
            python_path.chmod(0o755)
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr("nancy_brain.ocr_worker_runtime.subprocess.run", fake_run)

    summary = install_local_ocr_worker(root=tmp_path / "ocr-worker", verify=False)

    launcher = Path(summary.command[0])
    metadata = json.loads(summary.metadata_path.read_text(encoding="utf-8"))

    assert launcher.exists()
    assert launcher.name == "nancy-brain"
    assert worker_launcher_command(summary.root) == [str(launcher)]
    assert metadata["backend"] == "deepseek"
    assert metadata["verification"] is None
    assert any(command[1:3] == ["-m", "venv"] for command in commands)
    assert any(command[1:4] == ["-m", "pip", "install"] for command in commands)


def test_verify_local_ocr_worker_reports_backend_status(tmp_path, monkeypatch):
    root = tmp_path / "ocr-worker"
    python_path = root / "venv" / "bin" / "python"
    python_path.parent.mkdir(parents=True, exist_ok=True)
    python_path.write_text("", encoding="utf-8")
    python_path.chmod(0o755)

    def fake_run(cmd, check=False, capture_output=False, text=False, env=None):
        assert env is not None
        assert "PYTHONPATH" in env
        return subprocess.CompletedProcess(
            cmd,
            0,
            stdout=json.dumps(
                {
                    "name": "deepseek",
                    "available": True,
                    "reason": None,
                    "model": "deepseek-ai/DeepSeek-OCR",
                }
            ),
            stderr="",
        )

    monkeypatch.setattr("nancy_brain.ocr_worker_runtime.subprocess.run", fake_run)

    status = verify_local_ocr_worker(root)

    assert status["available"] is True
    assert status["name"] == "deepseek"
