from nancy_brain.utils_weights import validate_weights_mapping, validate_weights_config


def test_validate_weights_mapping_valid():
    ok, errs = validate_weights_mapping({".py": 1.0, ".md": "0.5"})
    assert ok is True
    assert errs == []


def test_validate_weights_mapping_invalid_non_numeric():
    ok, errs = validate_weights_mapping({".py": "abc"})
    assert ok is False
    assert any("not numeric" in e for e in errs)


def test_validate_weights_mapping_out_of_range():
    ok, errs = validate_weights_mapping({".py": 3.0, ".md": -0.1})
    assert ok is False
    assert any("not in range" in e for e in errs)


def test_validate_weights_config_sections():
    cfg = {
        "extensions": {".py": 1.0},
        "path_includes": {"tests": 1.2},
    }
    ok, errs = validate_weights_config(cfg)
    assert ok is True
    assert errs == []
