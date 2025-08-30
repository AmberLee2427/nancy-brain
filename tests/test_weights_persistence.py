import os
from pathlib import Path

import yaml

from nancy_brain.weights_persistence import load_model_weights, save_model_weights, set_model_weight


def test_load_missing_returns_empty(tmp_path):
    p = tmp_path / "model_weights.yaml"
    assert not p.exists()
    data = load_model_weights(p)
    assert isinstance(data, dict)
    assert data == {}


def test_save_and_load(tmp_path):
    p = tmp_path / "model_weights.yaml"
    mapping = {"doc/a": 1, "doc/b": "2"}
    save_model_weights(mapping, p)
    assert p.exists()
    loaded = load_model_weights(p)
    # Values should be coerced to floats
    assert loaded["doc/a"] == 1.0
    assert loaded["doc/b"] == 2.0


def test_set_model_weight_add_update_remove(tmp_path):
    p = tmp_path / "model_weights.yaml"
    # Add
    prev = set_model_weight(p, "x/1", 1.2)
    assert prev is None
    loaded = load_model_weights(p)
    assert loaded.get("x/1") == 1.2

    # Update
    prev2 = set_model_weight(p, "x/1", 1.5)
    assert float(prev2) == 1.2
    loaded = load_model_weights(p)
    assert loaded.get("x/1") == 1.5

    # Remove
    prev3 = set_model_weight(p, "x/1", None)
    assert float(prev3) == 1.5
    loaded = load_model_weights(p)
    assert "x/1" not in loaded


def test_load_invalid_content(tmp_path):
    p = tmp_path / "model_weights.yaml"
    # Write a YAML list (invalid for our loader)
    p.write_text(yaml.dump([1, 2, 3]))
    loaded = load_model_weights(p)
    assert loaded == {}


def test_coerce_invalid_value_skips(tmp_path):
    p = tmp_path / "model_weights.yaml"
    # Write mapping with a non-numeric value
    p.write_text(yaml.dump({"good": 2, "bad": "nope"}))
    loaded = load_model_weights(p)
    assert "good" in loaded and loaded["good"] == 2.0
    # 'bad' should be skipped during coercion
    assert "bad" not in loaded
