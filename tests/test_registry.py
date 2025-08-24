import pytest  # noqa: F401 E0401
import yaml  # noqa: F401 E0401
from pathlib import Path

from rag_core.registry import Registry
from rag_core.types import DocMeta


def test_registry_list_and_meta(tmp_path):
    # Create a temporary repositories.yml config
    config = {
        "cat1": [
            {"name": "repoA", "url": "https://github.com/user/repoA.git"},
        ],
        "cat2": [
            {"name": "repoB", "url": "https://example.com/user/repoB"},
        ],
    }
    cfg_file = tmp_path / "repositories.yml"
    cfg_file.write_text(yaml.safe_dump(config))

    registry = Registry(config_path=cfg_file)

    # list_ids without prefix should include both
    ids = registry.list_ids()
    assert set(ids) == {"cat1/repoA", "cat2/repoB"}

    # list_ids with prefix
    ids_prefixed = registry.list_ids(prefix="cat1")
    assert ids_prefixed == ["cat1/repoA"]

    # get_github_url truncates .git and uses blob/master
    url = registry.get_github_url("cat1/repoA/path/file.py")
    assert url == "https://github.com/user/repoA/blob/master/path/file.py"

    # Without .git suffix
    url2 = registry.get_github_url("cat2/repoB/dir/readme.md")
    assert url2 == "https://example.com/user/repoB/blob/master/dir/readme.md"

    # get_meta returns DocMeta with expected fields
    meta = registry.get_meta("cat1/repoA/file.txt")
    assert isinstance(meta, DocMeta)
    assert meta.doc_id == "cat1/repoA/file.txt"
    assert meta.github_url == "https://github.com/user/repoA/blob/master/file.txt"
    assert meta.default_branch == "master"
    assert meta.toolkit is None
    assert meta.doctype == "mixed" or meta.doctype in {"code", "docs"}
    assert meta.content_sha256 == ""
    assert meta.line_index == []

    # Unknown doc_id returns None URL and meta still valid
    meta2 = registry.get_meta("invalid/doc")
    assert isinstance(meta2, DocMeta)
    assert meta2.github_url == ""


@pytest.mark.parametrize(
    "prefix,expected",
    [
        ("", ["cat1/repoA", "cat2/repoB"]),
        ("cat1/repoA", ["cat1/repoA"]),
        ("nope", []),
    ],
)
def test_list_ids_various(prefix, expected, tmp_path):
    # reuse same config
    config = {
        "cat1": [{"name": "repoA", "url": "url"}],
        "cat2": [{"name": "repoB", "url": "url"}],
    }
    cfg_file = tmp_path / "repos.yml"
    cfg_file.write_text(yaml.safe_dump(config))
    registry = Registry(cfg_file)
    result = registry.list_ids(prefix=prefix)
    assert result == expected
