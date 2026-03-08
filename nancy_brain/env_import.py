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
            normalized = _normalize_github_url(url) if "github.com" in url.lower() else url.strip()
            urls.add(normalized)
    return urls


def import_from_env(
    env_file: str | Path,
    category: str | None,
    output_path: str | Path,
    dry_run: bool = False,
) -> dict:
    """
    Parse a conda environment.yml and add GitHub-backed packages to repositories.yml.

    Returns dict: {added: int, skipped_no_github: int, skipped_duplicate: int, errors: list[str]}
    """
    env_file_path = Path(env_file)
    output_file_path = Path(output_path)

    with open(env_file_path, "r", encoding="utf-8") as f:
        env = yaml.safe_load(f) or {}
    if not isinstance(env, dict):
        raise ValueError("environment.yml must contain a top-level mapping")

    env_name = env.get("name", "imported")
    effective_category = category or env_name

    pip_packages: list[str] = []
    for dep in env.get("dependencies", []):
        if isinstance(dep, dict) and "pip" in dep:
            pip_entries = dep.get("pip") or []
            if isinstance(pip_entries, list):
                pip_packages.extend([entry for entry in pip_entries if isinstance(entry, str)])

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

        category_entries.append(
            {
                "name": _repo_name_from_github_url(github_url),
                "url": github_url,
                "description": f"{package_name} - source from PyPI project_urls",
            }
        )
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
