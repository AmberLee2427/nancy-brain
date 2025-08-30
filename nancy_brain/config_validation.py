"""Simple configuration validators for repository and article YAML files.

These helpers are intentionally lightweight and dependency-free so they can
be used early in the CLI and CI to give clear error messages for malformed
configs.
"""

from typing import Any, Dict, List, Tuple


def _is_list_of_dicts(obj: Any) -> bool:
    return isinstance(obj, list) and all(isinstance(i, dict) for i in obj)


def validate_repositories_config(config: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """Validate the repositories config structure.

    Expected shape:
    {
      <category>: [
         {"name": "repo_name", "url": "https://..."},
         ...
      ],
      ...
    }

    Returns (valid, errors)
    """
    errors: List[str] = []
    if not isinstance(config, dict):
        return False, ["Root object must be a mapping of categories to lists"]
    for cat, entries in config.items():
        if not _is_list_of_dicts(entries):
            errors.append(f"Category '{cat}' must be a list of mapping entries")
            continue
        for idx, entry in enumerate(entries):
            if "name" not in entry:
                errors.append(f"{cat}[{idx}]: missing 'name'")
            if "url" not in entry:
                errors.append(f"{cat}[{idx}]: missing 'url'")
            else:
                if not isinstance(entry["url"], str) or not entry["url"].strip():
                    errors.append(f"{cat}[{idx}]: 'url' must be a non-empty string")
    return (len(errors) == 0), errors


def validate_articles_config(config: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """Validate articles config structure.

    Expected shape:
    {
      <category>: [
         {"name": "paper_id", "url": "https://...", "description": "..."},
      ]
    }
    """
    errors: List[str] = []
    if not isinstance(config, dict):
        return False, ["Root object must be a mapping of categories to lists"]
    for cat, entries in config.items():
        if not _is_list_of_dicts(entries):
            errors.append(f"Category '{cat}' must be a list of mapping entries")
            continue
        for idx, entry in enumerate(entries):
            if "name" not in entry:
                errors.append(f"{cat}[{idx}]: missing 'name'")
            if "url" not in entry:
                errors.append(f"{cat}[{idx}]: missing 'url'")
    return (len(errors) == 0), errors


__all__ = ["validate_repositories_config", "validate_articles_config"]
