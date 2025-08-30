from nancy_brain.config_validation import validate_repositories_config, validate_articles_config


def test_validate_repositories_config_good():
    cfg = {
        "docs": [
            {"name": "repo1", "url": "https://example.com/repo1.git"},
            {"name": "repo2", "url": "https://example.com/repo2.git"},
        ]
    }
    ok, errors = validate_repositories_config(cfg)
    assert ok
    assert errors == []


def test_validate_repositories_config_bad_shape():
    cfg = [1, 2, 3]
    ok, errors = validate_repositories_config(cfg)
    assert not ok
    assert "Root object must be a mapping" in errors[0]


def test_validate_repositories_config_missing_fields():
    cfg = {"docs": [{"name": "repo1"}, {"url": "https://x"}]}
    ok, errors = validate_repositories_config(cfg)
    assert not ok
    assert any("missing 'url'" in e or "missing 'name'" in e for e in errors)


def test_validate_articles_config_good():
    cfg = {"journal": [{"name": "paper1", "url": "https://x"}]}
    ok, errors = validate_articles_config(cfg)
    assert ok
    assert errors == []


def test_validate_articles_config_bad():
    cfg = {"journal": "notalist"}
    ok, errors = validate_articles_config(cfg)
    assert not ok
    assert any("must be a list" in e for e in errors)
