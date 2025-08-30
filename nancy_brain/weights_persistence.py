"""Helpers for loading/saving model_weights.yaml and performing single updates.

These helpers are intentionally small and file-system focused so they can be
unit-tested independently of Streamlit UI code.
"""

from pathlib import Path
import os
import yaml
from typing import Dict, Optional, Any


def load_model_weights(path: Path) -> Dict[str, float]:
    """Load model weights mapping from path. Returns empty dict on missing file.

    Non-dict YAML content is coerced to empty dict.
    """
    try:
        if not path.exists():
            return {}
        with open(path, "r") as f:
            data = yaml.safe_load(f) or {}
        if not isinstance(data, dict):
            return {}
        # Coerce numeric values to floats where possible
        out: Dict[str, float] = {}
        for k, v in data.items():
            try:
                out[k] = float(v)
            except Exception:
                # skip invalid values
                continue
        return out
    except Exception:
        return {}


def save_model_weights(mapping: Dict[str, Any], path: Path) -> None:
    """Write mapping to YAML file, ensuring parent dir exists.

    Values are not further validated here; callers should clamp/validate as
    appropriate.
    """
    os.makedirs(path.parent, exist_ok=True)
    with open(path, "w") as f:
        yaml.dump(mapping or {}, f, default_flow_style=False, sort_keys=False)


def set_model_weight(path: Path, doc_id: str, new_value: Optional[float]) -> Optional[float]:
    """Set a single doc's model weight. Returns previous value (or None).

    If new_value is None, the doc_id is removed from the mapping if present.
    """
    mapping = load_model_weights(path)
    prev = mapping.get(doc_id)
    if new_value is None:
        if doc_id in mapping:
            mapping.pop(doc_id)
    else:
        mapping[doc_id] = float(new_value)
    save_model_weights(mapping, path)
    return prev
