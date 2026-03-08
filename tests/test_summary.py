import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from dotenv import load_dotenv

from nancy_brain.summarization import SummaryGenerator, SummaryResult

load_dotenv("config/.env")


@pytest.mark.integration
def test_summary_on_readme(tmp_path, monkeypatch):
    """Ensure SummaryGenerator can produce a summary when ANTHROPIC_API_KEY is available."""

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        pytest.skip("ANTHROPIC_API_KEY not configured")
    monkeypatch.setenv("NB_USE_LOCAL_SUMMARY", "false")

    readme_path = Path("README.md")
    if not readme_path.exists():
        pytest.skip("README.md not present in repository")

    content = readme_path.read_text(encoding="utf-8")
    assert content.strip(), "README.md is empty"

    cache_dir = tmp_path / "summary_cache"
    summary_gen = SummaryGenerator(cache_dir=cache_dir, enabled=True)
    assert summary_gen.use_local is False

    result = summary_gen.summarize(
        doc_id="README.md",
        content=content,
        repo_name="nancy-brain",
        metadata={"file_type": ".md"},
    )
    if result is None and summary_gen.last_error_type == "connection":
        pytest.skip("Anthropic connection unavailable")
    assert result is not None, "Summarizer returned no result"
    assert isinstance(result.summary, str) and result.summary.strip(), "Summary text missing"
    assert isinstance(result.weight, float), "Summary weight missing"
    assert 0.5 <= result.weight <= 2.0, "Summary weight out of expected range"


@pytest.mark.parametrize(
    ("local_setting", "api_key", "expected_use_local", "expected_enabled"),
    [
        (None, None, False, False),
        (None, "test-key", False, True),
        ("false", None, False, False),
        ("false", "test-key", False, True),
        ("true", None, True, True),
        ("true", "test-key", True, True),
        ("1", "test-key", True, True),
        ("yes", "test-key", True, True),
        ("force", "test-key", True, True),
        ("forced", "test-key", True, True),
    ],
)
def test_summary_mode_selection(monkeypatch, tmp_path, local_setting, api_key, expected_use_local, expected_enabled):
    if local_setting is None:
        monkeypatch.delenv("NB_USE_LOCAL_SUMMARY", raising=False)
    else:
        monkeypatch.setenv("NB_USE_LOCAL_SUMMARY", local_setting)

    if api_key is None:
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    else:
        monkeypatch.setenv("ANTHROPIC_API_KEY", api_key)

    summary_gen = SummaryGenerator(cache_dir=Path(tmp_path) / "summaries", enabled=True)

    assert summary_gen.use_local is expected_use_local
    assert summary_gen.enabled is expected_enabled


# ---- Internal helper unit tests ----------------------------------------


def _make_gen(tmp_path, monkeypatch, *, api_key="test-key", local=False):
    """Helper: create a SummaryGenerator with an API key (or local mode)."""
    if api_key:
        monkeypatch.setenv("ANTHROPIC_API_KEY", api_key)
    else:
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    if local:
        monkeypatch.setenv("NB_USE_LOCAL_SUMMARY", "true")
    else:
        monkeypatch.setenv("NB_USE_LOCAL_SUMMARY", "false")
    return SummaryGenerator(cache_dir=tmp_path / "cache", enabled=True)


def test_trim_content_short(tmp_path, monkeypatch):
    """Content shorter than max_chars is returned unchanged."""
    gen = _make_gen(tmp_path, monkeypatch)
    result = gen._trim_content("hello", allow_extra=False)
    assert result == "hello"


def test_trim_content_long_no_extra(tmp_path, monkeypatch):
    """Content longer than max_chars is trimmed to max_chars."""
    gen = _make_gen(tmp_path, monkeypatch)
    long = "x" * (gen.max_chars + 100)
    trimmed = gen._trim_content(long, allow_extra=False)
    assert len(trimmed) == gen.max_chars


def test_trim_content_long_with_extra(tmp_path, monkeypatch):
    """With allow_extra=True the budget is extended by readme_bonus_chars."""
    gen = _make_gen(tmp_path, monkeypatch)
    long = "x" * (gen.max_chars + gen.readme_bonus_chars - 10)
    trimmed = gen._trim_content(long, allow_extra=True)
    assert len(trimmed) == len(long)


def test_trim_readme_none(tmp_path, monkeypatch):
    """_trim_readme returns None for None input."""
    gen = _make_gen(tmp_path, monkeypatch)
    assert gen._trim_readme(None) is None


def test_trim_readme_short(tmp_path, monkeypatch):
    """_trim_readme returns short strings unchanged."""
    gen = _make_gen(tmp_path, monkeypatch)
    assert gen._trim_readme("short readme") == "short readme"


def test_trim_readme_long(tmp_path, monkeypatch):
    """_trim_readme truncates to readme_bonus_chars."""
    gen = _make_gen(tmp_path, monkeypatch)
    long = "r" * (gen.readme_bonus_chars + 100)
    trimmed = gen._trim_readme(long)
    assert len(trimmed) == gen.readme_bonus_chars


def test_cache_key_deterministic(tmp_path, monkeypatch):
    """Same inputs always produce the same cache key."""
    gen = _make_gen(tmp_path, monkeypatch)
    key1 = gen._cache_key("doc/a.py", "content", None, None)
    key2 = gen._cache_key("doc/a.py", "content", None, None)
    assert key1 == key2


def test_cache_key_varies_by_input(tmp_path, monkeypatch):
    """Different inputs produce different cache keys."""
    gen = _make_gen(tmp_path, monkeypatch)
    key_a = gen._cache_key("doc/a.py", "content A", None, None)
    key_b = gen._cache_key("doc/b.py", "content A", None, None)
    key_c = gen._cache_key("doc/a.py", "content B", None, None)
    assert key_a != key_b
    assert key_a != key_c


def test_cache_key_with_readme(tmp_path, monkeypatch):
    """Including readme/readme_path changes the cache key."""
    gen = _make_gen(tmp_path, monkeypatch)
    base = gen._cache_key("doc/a.py", "content", None, None)
    with_readme = gen._cache_key("doc/a.py", "content", "readme text", None)
    with_path = gen._cache_key("doc/a.py", "content", "readme text", "README.md")
    assert base != with_readme
    assert with_readme != with_path


def test_strip_markdown_json_no_wrapping(tmp_path, monkeypatch):
    """Plain JSON passes through unchanged."""
    gen = _make_gen(tmp_path, monkeypatch)
    raw = '{"summary": "test", "weight": 1.0}'
    assert gen._strip_markdown_json(raw) == raw


def test_strip_markdown_json_with_backticks(tmp_path, monkeypatch):
    """JSON wrapped in ```json ... ``` is unwrapped."""
    gen = _make_gen(tmp_path, monkeypatch)
    raw = '```json\n{"summary": "test", "weight": 1.0}\n```'
    result = gen._strip_markdown_json(raw)
    parsed = json.loads(result)
    assert parsed["summary"] == "test"


def test_build_prompt_basic(tmp_path, monkeypatch):
    """_build_prompt returns a non-empty string with doc_id."""
    gen = _make_gen(tmp_path, monkeypatch)
    prompt = gen._build_prompt(
        doc_id="some/module.py",
        repo_name=None,
        repo_readme_path=None,
        repo_readme=None,
        metadata=None,
    )
    assert "some/module.py" in prompt
    assert isinstance(prompt, str)


def test_build_prompt_with_all_options(tmp_path, monkeypatch):
    """_build_prompt includes repo name, metadata, readme context."""
    gen = _make_gen(tmp_path, monkeypatch)
    prompt = gen._build_prompt(
        doc_id="repo/src/main.py",
        repo_name="test-repo",
        repo_readme_path="repo/README.md",
        repo_readme="This is the readme.",
        metadata={"file_type": ".py", "language": "Python"},
    )
    assert "test-repo" in prompt
    assert "repo/src/main.py" in prompt
    assert "This is the readme." in prompt
    assert "file_type" in prompt


def test_build_prompt_is_readme(tmp_path, monkeypatch):
    """When doc_id == repo_readme_path, prompt notes it IS the README."""
    gen = _make_gen(tmp_path, monkeypatch)
    prompt = gen._build_prompt(
        doc_id="repo/README.md",
        repo_name="test-repo",
        repo_readme_path="repo/README.md",
        repo_readme="Readme content.",
        metadata=None,
    )
    assert "README" in prompt


def test_create_client_no_api_key(tmp_path, monkeypatch):
    """_create_client returns None when API key is missing."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("NB_USE_LOCAL_SUMMARY", "false")
    gen = SummaryGenerator(cache_dir=tmp_path / "cache", enabled=False)
    gen.api_key = None
    result = gen._create_client()
    assert result is None


def test_create_client_anthropic_not_installed(tmp_path, monkeypatch):
    """_create_client returns None when anthropic is not importable."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("NB_USE_LOCAL_SUMMARY", "false")
    gen = SummaryGenerator(cache_dir=tmp_path / "cache", enabled=True)
    with patch.dict("sys.modules", {"anthropic": None}):
        result = gen._create_client()
    assert result is None


def test_create_client_with_api_key(tmp_path, monkeypatch):
    """_create_client returns an Anthropic client when key and SDK are available."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    monkeypatch.setenv("NB_USE_LOCAL_SUMMARY", "false")
    gen = SummaryGenerator(cache_dir=tmp_path / "cache", enabled=True)

    mock_anthropic_mod = MagicMock()
    mock_client = MagicMock()
    mock_anthropic_mod.Anthropic.return_value = mock_client

    with patch.dict("sys.modules", {"anthropic": mock_anthropic_mod}):
        result = gen._create_client()

    assert result is mock_client
    mock_anthropic_mod.Anthropic.assert_called_once_with(api_key="test-key")


def test_invoke_model_local_mode(tmp_path, monkeypatch):
    """_invoke_model delegates to _invoke_local when use_local is True."""
    gen = _make_gen(tmp_path, monkeypatch, local=True)
    gen._invoke_local = MagicMock(return_value={"summary": "local summary", "weight": 1.0})
    result = gen._invoke_model(prompt="prompt", content="content", readme=None, readme_path=None)
    assert result == {"summary": "local summary", "weight": 1.0}
    gen._invoke_local.assert_called_once()


def test_invoke_model_no_client(tmp_path, monkeypatch):
    """_invoke_model returns None when no API key is set (no client available)."""
    gen = _make_gen(tmp_path, monkeypatch)
    gen._create_client = MagicMock(return_value=None)
    result = gen._invoke_model(prompt="prompt", content="content", readme=None, readme_path=None)
    assert result is None


def test_invoke_model_success(tmp_path, monkeypatch):
    """_invoke_model parses JSON from a successful Anthropic API call."""
    gen = _make_gen(tmp_path, monkeypatch)

    mock_client = MagicMock()
    mock_block = MagicMock()
    mock_block.type = "text"
    mock_block.text = '{"summary": "Great module", "weight": 1.3}'
    mock_response = MagicMock()
    mock_response.content = [mock_block]
    mock_client.messages.create.return_value = mock_response
    gen._create_client = MagicMock(return_value=mock_client)

    result = gen._invoke_model(prompt="Summarize this", content="def foo(): pass", readme=None, readme_path=None)
    assert result is not None
    assert result["summary"] == "Great module"
    assert result["weight"] == pytest.approx(1.3)


def test_invoke_model_with_readme(tmp_path, monkeypatch):
    """_invoke_model includes readme context in the request."""
    gen = _make_gen(tmp_path, monkeypatch)

    mock_client = MagicMock()
    mock_block = MagicMock()
    mock_block.type = "text"
    mock_block.text = '{"summary": "With readme context", "weight": 1.1}'
    mock_response = MagicMock()
    mock_response.content = [mock_block]
    mock_client.messages.create.return_value = mock_response
    gen._create_client = MagicMock(return_value=mock_client)

    result = gen._invoke_model(
        prompt="Summarize this",
        content="content",
        readme="Repository readme",
        readme_path="README.md",
    )
    assert result is not None
    assert result["summary"] == "With readme context"
    # Verify the readme was included in the call
    call_args = mock_client.messages.create.call_args
    assert "README.md" in str(call_args)


def test_invoke_model_api_error_sets_last_error(tmp_path, monkeypatch):
    """_invoke_model sets last_error on API failure."""
    gen = _make_gen(tmp_path, monkeypatch)

    mock_client = MagicMock()
    mock_client.messages.create.side_effect = Exception("Connection refused")
    gen._create_client = MagicMock(return_value=mock_client)

    result = gen._invoke_model(prompt="prompt", content="content", readme=None, readme_path=None)
    assert result is None
    assert gen.last_error is not None
    assert gen.last_error_type == "connection"


def test_invoke_model_non_connection_error(tmp_path, monkeypatch):
    """_invoke_model sets last_error_type to None for non-connection errors."""
    gen = _make_gen(tmp_path, monkeypatch)

    mock_client = MagicMock()
    mock_client.messages.create.side_effect = ValueError("Bad response format")
    gen._create_client = MagicMock(return_value=mock_client)

    result = gen._invoke_model(prompt="prompt", content="content", readme=None, readme_path=None)
    assert result is None
    assert gen.last_error is not None
    assert gen.last_error_type is None


def test_summarize_disabled(tmp_path, monkeypatch):
    """summarize returns None when generator is disabled."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("NB_USE_LOCAL_SUMMARY", "false")
    gen = SummaryGenerator(cache_dir=tmp_path / "cache", enabled=False)
    assert not gen.enabled
    result = gen.summarize(doc_id="doc.py", content="some content")
    assert result is None


def test_summarize_empty_content(tmp_path, monkeypatch):
    """summarize returns None for empty/whitespace-only content."""
    gen = _make_gen(tmp_path, monkeypatch)
    assert gen.summarize(doc_id="doc.py", content="") is None
    assert gen.summarize(doc_id="doc.py", content="   ") is None


def test_summarize_cache_hit(tmp_path, monkeypatch):
    """summarize returns cached SummaryResult when cache file exists."""
    gen = _make_gen(tmp_path, monkeypatch)
    content = "def hello(): pass"
    cache_key = gen._cache_key("repo/doc.py", gen._trim_content(content, allow_extra=False), None, None)
    cache_file = gen.cache_dir / f"{cache_key}.json"
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    cache_file.write_text(
        json.dumps({"summary": "cached summary", "weight": 1.2, "model": "test"}),
        encoding="utf-8",
    )
    result = gen.summarize(doc_id="repo/doc.py", content=content)
    assert isinstance(result, SummaryResult)
    assert result.summary == "cached summary"
    assert result.weight == pytest.approx(1.2)
    assert result.cached is True


def test_summarize_invokes_model_and_caches(tmp_path, monkeypatch):
    """summarize calls _invoke_model and writes a cache file on success."""
    gen = _make_gen(tmp_path, monkeypatch)
    gen._invoke_model = MagicMock(return_value={"summary": "fresh summary", "weight": 1.5, "model": "test-model"})
    result = gen.summarize(doc_id="repo/doc.py", content="def bar(): pass")
    assert isinstance(result, SummaryResult)
    assert result.summary == "fresh summary"
    assert result.weight == pytest.approx(1.5)
    assert result.cached is False
    # Cache file should have been written
    assert any(gen.cache_dir.glob("*.json"))


def test_summarize_weight_clamped(tmp_path, monkeypatch):
    """summarize clamps weights outside [0.5, 2.0]."""
    gen = _make_gen(tmp_path, monkeypatch)
    gen._invoke_model = MagicMock(return_value={"summary": "test", "weight": 5.0, "model": "test"})
    result = gen.summarize(doc_id="doc.py", content="content")
    assert result is not None
    assert result.weight == pytest.approx(2.0)

    gen._invoke_model = MagicMock(return_value={"summary": "test", "weight": 0.1, "model": "test"})
    result2 = gen.summarize(doc_id="doc2.py", content="different content")
    assert result2 is not None
    assert result2.weight == pytest.approx(0.5)


def test_summarize_none_payload(tmp_path, monkeypatch):
    """summarize returns None when _invoke_model returns None."""
    gen = _make_gen(tmp_path, monkeypatch)
    gen._invoke_model = MagicMock(return_value=None)
    result = gen.summarize(doc_id="doc.py", content="content")
    assert result is None


def test_summarize_with_readme_args(tmp_path, monkeypatch):
    """summarize passes readme parameters through correctly."""
    gen = _make_gen(tmp_path, monkeypatch)
    gen._invoke_model = MagicMock(return_value={"summary": "with readme", "weight": 1.0, "model": "test"})
    result = gen.summarize(
        doc_id="repo/src/main.py",
        content="module content",
        repo_name="test-repo",
        repo_readme="# Readme",
        repo_readme_path="repo/README.md",
        repo_description="A test repo",
    )
    assert result is not None
    assert result.repo_readme_path == "repo/README.md"
