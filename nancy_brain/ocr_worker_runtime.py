"""Managed local OCR worker runtime helpers."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

WORKER_TORCH_VERSION = "2.6.0"
WORKER_TORCHVISION_VERSION = "0.21.0"
WORKER_TRANSFORMERS_VERSION = "4.46.3"
WORKER_TOKENIZERS_VERSION = "0.20.3"
WORKER_FLASH_ATTN_VERSION = "2.7.3"
WORKER_METADATA_FILENAME = "worker.json"

WORKER_CORE_REQUIREMENTS = [
    "pymupdf>=1.23.0",
    "pillow>=10.0.0",
]

DEEPSEEK_WORKER_REQUIREMENTS = [
    f"transformers=={WORKER_TRANSFORMERS_VERSION}",
    f"tokenizers=={WORKER_TOKENIZERS_VERSION}",
    "addict>=2.4.0",
    "easydict>=1.13",
    "einops>=0.8.0",
    "matplotlib>=3.8.0",
]


@dataclass(frozen=True)
class OCRWorkerInstallSummary:
    """Summary of a managed local OCR worker install."""

    root: Path
    python: Path
    command: list[str]
    code_root: Path
    metadata_path: Path
    backend: str
    torch_index_url: Optional[str]
    flash_attn: bool
    verification: Optional[dict] = None


def package_code_root() -> Path:
    """Return the import root that contains the `nancy_brain` package."""

    return Path(__file__).resolve().parent.parent


def windows_shared_worker_base() -> Path:
    """Return the shared worker base directory on Windows."""

    local_appdata = os.environ.get("LOCALAPPDATA", "").strip()
    if local_appdata:
        return Path(local_appdata) / "nancy-brain" / "ocr-worker"
    return Path.home() / "AppData" / "Local" / "nancy-brain" / "ocr-worker"


def default_shared_worker_root(root: Optional[Path | str] = None) -> Path:
    """Return the managed shared worker install root."""

    if root is not None:
        return Path(root).expanduser().resolve()
    if os.name == "nt":
        return windows_shared_worker_base()
    return Path.home() / ".local" / "share" / "nancy-brain" / "ocr-worker"


def worker_venv_dir(root: Optional[Path | str] = None) -> Path:
    return default_shared_worker_root(root) / "venv"


def worker_python_path(root: Optional[Path | str] = None) -> Path:
    venv_dir = worker_venv_dir(root)
    if os.name == "nt":
        return venv_dir / "Scripts" / "python.exe"
    return venv_dir / "bin" / "python"


def worker_launcher_dir(root: Optional[Path | str] = None) -> Path:
    install_root = default_shared_worker_root(root)
    return install_root / ("Scripts" if os.name == "nt" else "bin")


def worker_launcher_candidates(root: Optional[Path | str] = None) -> list[Path]:
    launcher_dir = worker_launcher_dir(root)
    if os.name == "nt":
        return [
            launcher_dir / "nancy-brain.exe",
            launcher_dir / "nancy-brain.cmd",
            launcher_dir / "nancy-brain",
        ]
    return [launcher_dir / "nancy-brain", launcher_dir / "nancy-brain.exe"]


def worker_launcher_command(root: Optional[Path | str] = None) -> Optional[list[str]]:
    """Return the managed shared worker launcher command if installed."""

    for candidate in worker_launcher_candidates(root):
        if not candidate.exists():
            continue
        if os.name != "nt" and not os.access(candidate, os.X_OK):
            continue
        return [str(candidate)]
    return None


def worker_metadata_path(root: Optional[Path | str] = None) -> Path:
    return default_shared_worker_root(root) / WORKER_METADATA_FILENAME


def read_worker_metadata(root: Optional[Path | str] = None) -> Optional[dict]:
    metadata_path = worker_metadata_path(root)
    if not metadata_path.exists():
        return None
    try:
        return json.loads(metadata_path.read_text(encoding="utf-8"))
    except Exception:
        return None


def detect_torch_index_url() -> Optional[str]:
    """Best-effort torch wheel index detection from the current environment."""

    env_override = os.environ.get("NB_OCR_TORCH_INDEX_URL", "").strip()
    if env_override:
        return env_override

    try:
        import torch
    except Exception:
        return None

    cuda_version = getattr(getattr(torch, "version", None), "cuda", None)
    if not cuda_version:
        return None
    tag = f"cu{str(cuda_version).replace('.', '')}"
    return f"https://download.pytorch.org/whl/{tag}"


def install_local_ocr_worker(
    *,
    root: Optional[Path | str] = None,
    python_executable: Optional[str | Path] = None,
    backend: str = "deepseek",
    recreate: bool = False,
    torch_index_url: Optional[str] = None,
    flash_attn: bool = False,
    verify: bool = True,
) -> OCRWorkerInstallSummary:
    """Create or update the managed local OCR worker runtime."""

    install_root = default_shared_worker_root(root)
    install_root.mkdir(parents=True, exist_ok=True)
    venv_dir = worker_venv_dir(install_root)
    if recreate and venv_dir.exists():
        shutil.rmtree(venv_dir)

    installer_python = str(Path(python_executable).expanduser()) if python_executable else sys.executable
    if not venv_dir.exists():
        subprocess.run([installer_python, "-m", "venv", str(venv_dir)], check=True)

    worker_python = worker_python_path(install_root)
    _pip_install(worker_python, ["pip>=24.0", "setuptools>=68.0", "wheel>=0.42.0"])
    _pip_install(worker_python, WORKER_CORE_REQUIREMENTS)

    resolved_torch_index = torch_index_url or detect_torch_index_url()
    if backend == "deepseek":
        _install_deepseek_runtime(worker_python, resolved_torch_index, flash_attn)
    else:
        raise ValueError(f"unsupported OCR worker backend: {backend}")

    code_root = package_code_root()
    _write_worker_launchers(install_root, code_root=code_root, worker_python=worker_python)
    verification = verify_local_ocr_worker(install_root, code_root=code_root, backend=backend) if verify else None

    metadata = {
        "installed_at": datetime.now(timezone.utc).isoformat(),
        "backend": backend,
        "code_root": str(code_root),
        "python": str(worker_python),
        "command": worker_launcher_command(install_root),
        "torch_index_url": resolved_torch_index,
        "flash_attn": flash_attn,
        "verification": verification,
    }
    metadata_path = worker_metadata_path(install_root)
    metadata_path.write_text(json.dumps(metadata, indent=2, sort_keys=True), encoding="utf-8")

    return OCRWorkerInstallSummary(
        root=install_root,
        python=worker_python,
        command=worker_launcher_command(install_root) or [],
        code_root=code_root,
        metadata_path=metadata_path,
        backend=backend,
        torch_index_url=resolved_torch_index,
        flash_attn=flash_attn,
        verification=verification,
    )


def inspect_local_ocr_worker(
    *,
    root: Optional[Path | str] = None,
    verify: bool = False,
    backend: str = "deepseek",
) -> dict:
    """Inspect the managed local OCR worker runtime."""

    install_root = default_shared_worker_root(root)
    command = worker_launcher_command(install_root)
    python_path = worker_python_path(install_root)
    metadata = read_worker_metadata(install_root)
    verification = verify_local_ocr_worker(install_root, backend=backend) if verify and python_path.exists() else None
    return {
        "root": install_root,
        "python": python_path,
        "command": command,
        "metadata": metadata,
        "installed": command is not None and python_path.exists(),
        "verification": verification,
    }


def verify_local_ocr_worker(
    root: Optional[Path | str] = None,
    *,
    code_root: Optional[Path | str] = None,
    backend: str = "deepseek",
) -> dict:
    """Verify that the managed worker can import the OCR backend stack."""

    install_root = default_shared_worker_root(root)
    worker_python = worker_python_path(install_root)
    runtime_code_root = Path(code_root).resolve() if code_root is not None else package_code_root()
    env = _worker_env(runtime_code_root)
    script = (
        "import json; "
        "from nancy_brain.pdf_ocr import get_pdf_ocr_backend_status; "
        f"status = get_pdf_ocr_backend_status({backend!r}); "
        "print(json.dumps({"
        "'name': status.name, "
        "'available': status.available, "
        "'reason': status.reason, "
        "'model': status.model"
        "}, sort_keys=True))"
    )
    try:
        completed = subprocess.run(
            [str(worker_python), "-c", script],
            check=False,
            capture_output=True,
            text=True,
            env=env,
        )
    except Exception as exc:
        return {
            "available": False,
            "name": backend,
            "reason": f"failed to launch worker python: {exc}",
            "model": None,
        }

    stdout = completed.stdout.strip()
    try:
        payload = json.loads(stdout) if stdout else {}
    except Exception:
        payload = {}

    if not payload:
        payload = {
            "available": False,
            "name": backend,
            "reason": completed.stderr.strip() or "worker verification did not return JSON",
            "model": None,
        }
    return payload


def _install_deepseek_runtime(worker_python: Path, torch_index_url: Optional[str], flash_attn: bool) -> None:
    torch_requirements = [
        f"torch=={WORKER_TORCH_VERSION}",
        f"torchvision=={WORKER_TORCHVISION_VERSION}",
    ]
    _pip_install(worker_python, torch_requirements, index_url=torch_index_url)
    _pip_install(worker_python, DEEPSEEK_WORKER_REQUIREMENTS)
    if flash_attn:
        _pip_install(
            worker_python,
            [f"flash-attn=={WORKER_FLASH_ATTN_VERSION}"],
            extra_args=["--no-build-isolation"],
        )


def _pip_install(
    worker_python: Path,
    requirements: list[str],
    *,
    index_url: Optional[str] = None,
    extra_args: Optional[list[str]] = None,
) -> None:
    if not requirements:
        return
    cmd = [str(worker_python), "-m", "pip", "install", "--upgrade", *requirements]
    if index_url:
        cmd.extend(["--index-url", index_url])
    if extra_args:
        cmd.extend(extra_args)
    subprocess.run(cmd, check=True)


def _write_worker_launchers(install_root: Path, *, code_root: Path, worker_python: Path) -> None:
    launcher_dir = worker_launcher_dir(install_root)
    launcher_dir.mkdir(parents=True, exist_ok=True)

    if os.name == "nt":
        cmd_path = launcher_dir / "nancy-brain.cmd"
        cmd_path.write_text(
            _windows_launcher_contents(code_root=code_root, worker_python=worker_python), encoding="utf-8"
        )
    else:
        launcher_path = launcher_dir / "nancy-brain"
        launcher_path.write_text(
            _unix_launcher_contents(code_root=code_root, worker_python=worker_python), encoding="utf-8"
        )
        launcher_path.chmod(0o755)


def _worker_env(code_root: Path) -> dict[str, str]:
    env = os.environ.copy()
    existing = env.get("PYTHONPATH", "").strip()
    env["PYTHONPATH"] = str(code_root) if not existing else f"{code_root}{os.pathsep}{existing}"
    return env


def _unix_launcher_contents(*, code_root: Path, worker_python: Path) -> str:
    return (
        "#!/usr/bin/env sh\n"
        f'PYTHONPATH="{code_root}${{PYTHONPATH:+:${{PYTHONPATH}}}}"\n'
        "export PYTHONPATH\n"
        f'exec "{worker_python}" -m nancy_brain.ocr_worker_entry "$@"\n'
    )


def _windows_launcher_contents(*, code_root: Path, worker_python: Path) -> str:
    return (
        "@echo off\r\n"
        f'set "PYTHONPATH={code_root};%PYTHONPATH%"\r\n'
        f'"{worker_python}" -m nancy_brain.ocr_worker_entry %*\r\n'
    )
