"""Tests for managed OCR worker runtime helpers."""

import importlib
import json
import subprocess
import sys
import tomllib
from pathlib import Path

from nancy_brain.ocr_worker_runtime import (
    install_local_ocr_worker,
    verify_local_ocr_worker,
    worker_launcher_command,
)


def test_install_local_ocr_worker_writes_launcher_and_metadata(tmp_path, monkeypatch):
    commands: list[list[str]] = []

    def fake_run(cmd, check=False, capture_output=False, text=False, env=None, cwd=None):
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
    assert summary.code_root == summary.root / "code"
    assert (summary.code_root / "nancy_brain" / "__init__.py").exists()
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

    def fake_run(cmd, check=False, capture_output=False, text=False, env=None, cwd=None):
        assert env is not None
        assert "PYTHONPATH" in env
        assert str(root / "code") in env["PYTHONPATH"]
        assert cwd == str(root)
        assert "ensure_loaded" in cmd[2]
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


def test_verify_local_ocr_worker_reports_model_load_failure(tmp_path, monkeypatch):
    root = tmp_path / "ocr-worker"
    python_path = root / "venv" / "bin" / "python"
    python_path.parent.mkdir(parents=True, exist_ok=True)
    python_path.write_text("", encoding="utf-8")
    python_path.chmod(0o755)

    def fake_run(cmd, check=False, capture_output=False, text=False, env=None, cwd=None):
        return subprocess.CompletedProcess(
            cmd,
            0,
            stdout=json.dumps(
                {
                    "name": "deepseek",
                    "available": False,
                    "reason": "CUDA out of memory",
                    "model": "deepseek-ai/DeepSeek-OCR",
                }
            ),
            stderr="",
        )

    monkeypatch.setattr("nancy_brain.ocr_worker_runtime.subprocess.run", fake_run)

    status = verify_local_ocr_worker(root)

    assert status["available"] is False
    assert status["reason"] == "CUDA out of memory"


def test_install_local_ocr_worker_falls_back_to_unpinned_torch_when_default_pin_missing(tmp_path, monkeypatch):
    commands: list[list[str]] = []
    pip_installs: list[list[str]] = []

    def fake_run(cmd, check=False, capture_output=False, text=False, env=None, cwd=None):
        command = [str(part) for part in cmd]
        commands.append(command)
        if len(command) >= 4 and command[1:3] == ["-m", "venv"]:
            venv_dir = Path(command[3])
            python_path = venv_dir / "bin" / "python"
            python_path.parent.mkdir(parents=True, exist_ok=True)
            python_path.write_text("", encoding="utf-8")
            python_path.chmod(0o755)
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        if len(command) >= 4 and command[1:4] == ["-m", "pip", "install"]:
            pip_installs.append(command)
            if "torch==2.6.0" in command:
                raise subprocess.CalledProcessError(returncode=1, cmd=cmd)
            return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
        if len(command) >= 3 and command[1] == "-c" and "torch.__version__" in command[2]:
            return subprocess.CompletedProcess(
                cmd,
                0,
                stdout=json.dumps({"torch_version": "2.10.0+cu128", "torchvision_version": "0.25.0+cu128"}),
                stderr="",
            )
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")

    monkeypatch.setattr("nancy_brain.ocr_worker_runtime.subprocess.run", fake_run)

    summary = install_local_ocr_worker(root=tmp_path / "ocr-worker", verify=False)

    assert summary.torch_fallback_used is True
    assert summary.torch_version == "2.10.0+cu128"
    assert summary.torchvision_version == "0.25.0+cu128"
    assert (summary.code_root / "nancy_brain" / "pdf_ocr.py").exists()
    assert any("torch==2.6.0" in command for command in pip_installs)
    assert any(
        command[index : index + 2] == ["torch", "torchvision"]
        for command in pip_installs
        for index in range(len(command) - 1)
    )


def test_package_root_import_does_not_eagerly_import_cli(monkeypatch):
    original_module = sys.modules.pop("nancy_brain", None)
    original_cli_module = sys.modules.pop("nancy_brain.cli", None)
    try:
        package = importlib.import_module("nancy_brain")
        project = tomllib.loads((Path(__file__).parents[1] / "pyproject.toml").read_text(encoding="utf-8"))
        assert package.__version__ == project["project"]["version"]
        assert "nancy_brain.cli" not in sys.modules
    finally:
        sys.modules.pop("nancy_brain", None)
        sys.modules.pop("nancy_brain.cli", None)
        if original_module is not None:
            sys.modules["nancy_brain"] = original_module
        if original_cli_module is not None:
            sys.modules["nancy_brain.cli"] = original_cli_module
