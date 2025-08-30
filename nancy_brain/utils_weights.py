"""Utility helpers for validating weight configs."""

from typing import Dict, Tuple, List, Any


def validate_weights_mapping(mapping: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """Validate that provided mapping values are numbers between 0 and 2.

    Returns (is_valid, errors).
    """
    errors = []
    if not isinstance(mapping, dict):
        return False, ["Weights must be a mapping/dictionary"]

    for k, v in mapping.items():
        try:
            num = float(v)
        except Exception:
            errors.append(f"Key '{k}': value '{v}' is not numeric")
            continue
        if not (0.0 <= num <= 2.0):
            errors.append(f"Key '{k}': value {num} not in range [0, 2]")

    return (len(errors) == 0), errors


def validate_weights_config(cfg: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """Validate a full weights config with top-level 'extensions' and 'path_includes'."""
    errors = []
    if not isinstance(cfg, dict):
        return False, ["Top-level weights config must be a mapping"]

    for section in ("extensions", "path_includes"):
        sec = cfg.get(section, {})
        ok, errs = validate_weights_mapping(sec if sec is not None else {})
        if not ok:
            errors.extend([f"{section}: {e}" for e in errs])

    return (len(errors) == 0), errors
