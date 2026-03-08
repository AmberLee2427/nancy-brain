"""Helpers to import GitHub-backed dependencies from a conda environment.yml."""

from __future__ import annotations

from pathlib import Path
import re
import time
from typing import Any, Optional
from urllib.parse import urlparse

import requests
import yaml

PRIORITY_URL_KEYS = ("Source", "Source Code", "Homepage", "Repository")


def _is_skippable_pip_spec(spec: str) -> bool:
    lowered = spec.strip().lower()
    if not lowered:
        return True
    if lowered == ".":
        return True
    if lowered.startswith("-e") or lowered.startswith("-r"):
        return True
    if lowered.startswith("http") or lowered.startswith("git+"):
        return True
    if lowered.startswith("--"):
        return True
    return False


def _package_name_from_pip_spec(spec: str) -> Optional[str]:
    if _is_skippable_pip_spec(spec):
        return None
    package_name = re.split(r"[=<>!~\[]", spec, maxsplit=1)[0].strip()
    if not package_name or package_name.startswith("-"):
        return None
    return package_name


def _normalize_github_url(raw_url: str) -> Optional[str]:
    if not isinstance(raw_url, str):
        return None
    cleaned = raw_url.strip()
    if not cleaned:
        return None
    if cleaned.lower().startswith("git+"):
        cleaned = cleaned[4:]
    # Handle SCM-style refs like git@github.com:owner/repo.git
    ssh_match = re.search(r"github\.com[:/]+([^/\s]+)/([^/\s#?]+)", cleaned, flags=re.IGNORECASE)
    if ssh_match:
        owner = ssh_match.group(1)
        repo = ssh_match.group(2)
    else:
        if "://" not in cleaned and cleaned.startswith("github.com/"):
            cleaned = f"https://{cleaned}"
        parsed = urlparse(cleaned)
        host = parsed.netloc.lower()
        if host.startswith("www."):
            host = host[4:]
        if host != "github.com":
            return None
        parts = [part for part in parsed.path.split("/") if part]
        if len(parts) < 2:
            return None
        owner, repo = parts[0], parts[1]
    repo = re.sub(r"\.git$", "", repo, flags=re.IGNORECASE)
    if not owner or not repo:
        return None
    return f"https://github.com/{owner}/{repo}"


def _extract_github_url(payload: dict[str, Any]) -> Optional[str]:
    info = payload.get("info") or {}
    project_urls = info.get("project_urls") or {}
    if not isinstance(project_urls, dict):
        return None

    seen_keys: set[str] = set()
    for key in PRIORITY_URL_KEYS:
        seen_keys.add(key)
        value = project_urls.get(key)
        if isinstance(value, str) and "github.com" in value.lower():
            normalized = _normalize_github_url(value)
            if normalized:
                return normalized

    for key, value in project_urls.items():
        if key in seen_keys:
            continue
        if isinstance(value, str) and "github.com" in value.lower():
            normalized = _normalize_github_url(value)
            if normalized:
                return normalized

    # Fallback: check info.home_page (older packages only have this field)
    home_page = info.get("home_page") or ""
    if isinstance(home_page, str) and "github.com" in home_page.lower():
        normalized = _normalize_github_url(home_page)
        if normalized:
            return normalized
    return None


def _repo_name_from_github_url(github_url: str) -> str:
    parsed = urlparse(github_url)
    parts = [part for part in parsed.path.split("/") if part]
    owner, repo = parts[0], parts[1]
    return f"{owner}_{repo}".lower().replace("-", "_")


def _iter_existing_urls(config: dict[str, Any]) -> set[str]:
    urls: set[str] = set()
    for entries in config.values():
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            url = entry.get("url")
            if not isinstance(url, str) or not url.strip():
                continue
            if "github.com" in url.lower():
                normalized = _normalize_github_url(url)
                if normalized:
                    urls.add(normalized)
                else:
                    urls.add(url.strip())
            else:
                urls.add(url.strip())
    return urls


def _version_from_pip_spec(spec: str) -> Optional[str]:
    """Return the exact version from a ``==`` pinned pip spec, or None."""
    m = re.search(r"==([^\s,;]+)", spec)
    return m.group(1).strip() if m else None


def _parse_requirements_lines(lines: list[str]) -> list[str]:
    """Return pip requirement specs parsed from raw requirements.txt lines."""
    specs: list[str] = []
    for line in lines:
        line = re.sub(r"\s*#.*$", "", line).strip()
        if not line:
            continue
        # Skip -r/-c file includes and bare flags like --extra-index-url
        if line.startswith("-r ") or line.startswith("-c ") or line.startswith("--"):
            continue
        specs.append(line)
    return specs


def _load_toml(path: Path) -> dict:
    """Load a TOML file using tomllib (3.11+) or the tomli back-compat package."""
    try:
        import tomllib  # type: ignore[import]
    except ImportError:
        try:
            import tomli as tomllib  # type: ignore[no-redef]
        except ImportError:
            raise ImportError(
                "tomllib (Python 3.11+) or tomli is required to parse pyproject.toml. "
                "Install with: pip install tomli"
            )
    with open(path, "rb") as f:
        return tomllib.load(f)


def _parse_pyproject_deps(path: Path) -> tuple[list[str], Optional[str]]:
    """
    Extract dependency specifiers from a pyproject.toml.

    Returns ``(specs, project_name)`` where *project_name* may be None.
    Handles PEP 621 ``[project].dependencies`` and Poetry
    ``[tool.poetry.dependencies]``.
    """
    data = _load_toml(path)
    specs: list[str] = []

    # PEP 621
    project_deps = data.get("project", {}).get("dependencies", [])
    if isinstance(project_deps, list):
        specs.extend([d for d in project_deps if isinstance(d, str)])

    # Poetry
    poetry_deps = data.get("tool", {}).get("poetry", {}).get("dependencies", {})
    if isinstance(poetry_deps, dict):
        for pkg, constraint in poetry_deps.items():
            if pkg.lower() == "python":
                continue
            if isinstance(constraint, str):
                if constraint.startswith("=="):
                    specs.append(f"{pkg}{constraint}")
                elif re.match(r"^\d", constraint):
                    specs.append(f"{pkg}=={constraint}")
                else:
                    specs.append(pkg)
            elif isinstance(constraint, dict):
                version = constraint.get("version", "")
                if version.startswith("=="):
                    specs.append(f"{pkg}{version}")
                elif re.match(r"^\d", version):
                    specs.append(f"{pkg}=={version}")
                else:
                    specs.append(pkg)

    project_name: Optional[str] = data.get("project", {}).get("name") or data.get("tool", {}).get("poetry", {}).get(
        "name"
    )
    return specs, project_name


def _import_package_list(
    pip_packages: list[str],
    effective_category: str,
    output_file_path: Path,
    dry_run: bool,
    pin_versions: bool,
) -> dict:
    """
    Core PyPI lookup loop shared by all ``import_from_*`` functions.

    Returns dict: {added, skipped_no_github, skipped_duplicate, errors}
    """
    if output_file_path.exists():
        with open(output_file_path, "r", encoding="utf-8") as f:
            repositories = yaml.safe_load(f) or {}
        if not isinstance(repositories, dict):
            raise ValueError("repositories.yml must contain a top-level mapping")
    else:
        repositories = {}

    existing_urls = _iter_existing_urls(repositories)
    category_entries = repositories.setdefault(effective_category, [])
    if not isinstance(category_entries, list):
        raise ValueError(f"Category '{effective_category}' in repositories.yml must be a list")

    added = 0
    skipped_no_github = 0
    skipped_duplicate = 0
    errors: list[str] = []

    for raw_spec in pip_packages:
        package_name = _package_name_from_pip_spec(raw_spec)
        if not package_name:
            continue

        try:
            response = requests.get(f"https://pypi.org/pypi/{package_name}/json", timeout=10)
            response.raise_for_status()
            payload = response.json()
        except Exception as exc:
            errors.append(f"{package_name}: {exc}")
            time.sleep(0.1)
            continue

        github_url = _extract_github_url(payload)
        if not github_url:
            skipped_no_github += 1
            time.sleep(0.1)
            continue

        if github_url in existing_urls:
            skipped_duplicate += 1
            time.sleep(0.1)
            continue

        entry: dict[str, Any] = {
            "name": _repo_name_from_github_url(github_url),
            "url": github_url,
            "description": f"{package_name} - source from PyPI project_urls",
        }
        if pin_versions:
            version = _version_from_pip_spec(raw_spec)
            if version:
                entry["ref"] = version

        category_entries.append(entry)
        existing_urls.add(github_url)
        added += 1
        time.sleep(0.1)

    if not dry_run:
        output_file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_file_path, "w", encoding="utf-8") as f:
            yaml.dump(repositories, f, default_flow_style=False, sort_keys=False)

    return {
        "added": added,
        "skipped_no_github": skipped_no_github,
        "skipped_duplicate": skipped_duplicate,
        "errors": errors,
    }


def import_from_env(
    env_file: str | Path,
    category: str | None,
    output_path: str | Path,
    dry_run: bool = False,
    pin_versions: bool = False,
) -> dict:
    """
    Parse a conda ``environment.yml`` and add GitHub-backed packages to
    ``repositories.yml``.

    Returns dict: {added, skipped_no_github, skipped_duplicate, errors}
    """
    env_file_path = Path(env_file)

    with open(env_file_path, "r", encoding="utf-8") as f:
        env = yaml.safe_load(f) or {}
    if not isinstance(env, dict):
        raise ValueError("environment.yml must contain a top-level mapping")

    effective_category = category or env.get("name", "imported")

    pip_packages: list[str] = []
    for dep in env.get("dependencies", []):
        if isinstance(dep, dict) and "pip" in dep:
            pip_entries = dep.get("pip") or []
            if isinstance(pip_entries, list):
                pip_packages.extend([e for e in pip_entries if isinstance(e, str)])

    return _import_package_list(pip_packages, effective_category, Path(output_path), dry_run, pin_versions)


def import_from_requirements(
    req_file: str | Path,
    category: str | None,
    output_path: str | Path,
    dry_run: bool = False,
    pin_versions: bool = False,
) -> dict:
    """
    Parse a ``requirements.txt`` (or ``.in``) file and add GitHub-backed
    packages to ``repositories.yml``.

    Returns dict: {added, skipped_no_github, skipped_duplicate, errors}
    """
    req_path = Path(req_file)
    lines = req_path.read_text(encoding="utf-8").splitlines()
    pip_packages = _parse_requirements_lines(lines)
    effective_category = category or req_path.stem

    return _import_package_list(pip_packages, effective_category, Path(output_path), dry_run, pin_versions)


def import_from_pyproject(
    toml_file: str | Path,
    category: str | None,
    output_path: str | Path,
    dry_run: bool = False,
    pin_versions: bool = False,
) -> dict:
    """
    Parse a ``pyproject.toml`` (PEP 621 or Poetry) and add GitHub-backed
    packages to ``repositories.yml``.

    Returns dict: {added, skipped_no_github, skipped_duplicate, errors}
    """
    toml_path = Path(toml_file)
    pip_packages, project_name = _parse_pyproject_deps(toml_path)
    effective_category = category or project_name or toml_path.stem

    return _import_package_list(pip_packages, effective_category, Path(output_path), dry_run, pin_versions)


def import_from_file(
    file_path: str | Path,
    category: str | None = None,
    output_path: str | Path = "config/repositories.yml",
    dry_run: bool = False,
    pin_versions: bool = False,
) -> dict:
    """
    Auto-detect the dependency file format and import GitHub-backed packages
    into ``repositories.yml``.

    Supported formats:
    - conda ``environment.yml`` / ``*.yaml``
    - ``requirements.txt`` / ``requirements.in`` / ``*.txt``
    - ``pyproject.toml``

    Returns dict: {added, skipped_no_github, skipped_duplicate, errors}
    """
    path = Path(file_path)
    name = path.name.lower()
    suffix = path.suffix.lower()

    if name == "pyproject.toml" or suffix == ".toml":
        return import_from_pyproject(path, category, output_path, dry_run, pin_versions)
    elif suffix in (".txt", ".in") or "requirements" in name:
        return import_from_requirements(path, category, output_path, dry_run, pin_versions)
    elif suffix in (".yml", ".yaml"):
        return import_from_env(path, category, output_path, dry_run, pin_versions)
    else:
        raise ValueError(
            f"Unrecognised file format: {path.name}. " "Supported: environment.yml, requirements.txt, pyproject.toml"
        )
