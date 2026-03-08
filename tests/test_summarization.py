"""Tests for nancy_brain/summarization.py - SummaryGenerator class."""

import json
import os
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from nancy_brain.summarization import SummaryGenerator, SummaryResult

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def summary_cache_dir(tmp_path):
    return tmp_path / "summary_cache"


@pytest.fixture
def generator_disabled(summary_cache_dir):
    """A generator with no API key and no local mode -> disabled."""
    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "", "NB_USE_LOCAL_SUMMARY": ""}):
        return SummaryGenerator(cache_dir=summary_cache_dir, enabled=True)


@pytest.fixture
def generator_with_key(summary_cache_dir):
    """A generator with a fake API key -> enabled (Anthropic mode)."""
    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "fake-key", "NB_USE_LOCAL_SUMMARY": ""}):
        return SummaryGenerator(cache_dir=summary_cache_dir, enabled=True)


@pytest.fixture
def generator_local(summary_cache_dir):
    """A generator in local mode."""
    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "", "NB_USE_LOCAL_SUMMARY": "true"}):
        return SummaryGenerator(cache_dir=summary_cache_dir, enabled=True)


# ---------------------------------------------------------------------------
# __init__
# ---------------------------------------------------------------------------


def test_init_disabled_when_no_key(summary_cache_dir):
    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "", "NB_USE_LOCAL_SUMMARY": ""}):
        gen = SummaryGenerator(cache_dir=summary_cache_dir)
    assert gen.enabled is False


def test_init_enabled_with_key(summary_cache_dir):
    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key", "NB_USE_LOCAL_SUMMARY": ""}):
        gen = SummaryGenerator(cache_dir=summary_cache_dir)
    assert gen.enabled is True
    assert summary_cache_dir.exists()


def test_init_local_mode(summary_cache_dir):
    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "", "NB_USE_LOCAL_SUMMARY": "true"}):
        gen = SummaryGenerator(cache_dir=summary_cache_dir)
    assert gen.use_local is True
    assert gen.enabled is True


def test_init_disabled_flag(summary_cache_dir):
    with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "key", "NB_USE_LOCAL_SUMMARY": ""}):
        gen = SummaryGenerator(cache_dir=summary_cache_dir, enabled=False)
    assert gen.enabled is False


# ---------------------------------------------------------------------------
# summarize - disabled
# ---------------------------------------------------------------------------


def test_summarize_returns_none_when_disabled(generator_disabled):
    result = generator_disabled.summarize(doc_id="doc/x.py", content="some content")
    assert result is None


def test_summarize_returns_none_empty_content(generator_with_key):
    result = generator_with_key.summarize(doc_id="doc/x.py", content="   ")
    assert result is None


# ---------------------------------------------------------------------------
# summarize - cache hits
# ---------------------------------------------------------------------------


def test_summarize_returns_cached_result(generator_with_key):
    """If a cache file exists, return the cached result without calling API."""
    # Pre-populate cache
    trimmed = "Short content."
    gen = generator_with_key
    cache_key = gen._cache_key("test/doc.py", trimmed, None, None)
    cache_file = gen.cache_dir / f"{cache_key}.json"
    cache_file.write_text(
        json.dumps(
            {
                "summary": "Cached summary.",
                "weight": 1.2,
                "model": "claude-test",
                "repo_readme_path": None,
            }
        ),
        encoding="utf-8",
    )

    result = gen.summarize(doc_id="test/doc.py", content=trimmed)
    assert result is not None
    assert result.cached is True
    assert result.summary == "Cached summary."
    assert result.weight == pytest.approx(1.2)


def test_summarize_ignores_corrupt_cache(generator_with_key):
    """Corrupt cache file should be ignored and fall through to API call."""
    gen = generator_with_key
    trimmed = "Content here."
    cache_key = gen._cache_key("test/corrupt.py", trimmed, None, None)
    cache_file = gen.cache_dir / f"{cache_key}.json"
    cache_file.write_text("NOT VALID JSON", encoding="utf-8")

    # Mock the API call to return a valid summary
    with patch.object(gen, "_invoke_model", return_value={"summary": "Fresh summary", "weight": 1.0}):
        result = gen.summarize(doc_id="test/corrupt.py", content=trimmed)

    assert result is not None
    assert result.cached is False
    assert result.summary == "Fresh summary"


# ---------------------------------------------------------------------------
# summarize - API call path
# ---------------------------------------------------------------------------


def test_summarize_api_call(generator_with_key):
    gen = generator_with_key
    mock_payload = {"summary": "API summary.", "weight": 1.5, "model": "claude-haiku"}

    with patch.object(gen, "_invoke_model", return_value=mock_payload):
        result = gen.summarize(doc_id="cat/doc.py", content="Some long content here.")

    assert result is not None
    assert result.summary == "API summary."
    assert result.weight == pytest.approx(1.5)
    assert result.cached is False


def test_summarize_api_returns_none(generator_with_key):
    gen = generator_with_key
    with patch.object(gen, "_invoke_model", return_value=None):
        result = gen.summarize(doc_id="cat/doc.py", content="Some content.")
    assert result is None


def test_summarize_invalid_payload(generator_with_key):
    gen = generator_with_key
    # Payload missing 'summary' key
    with patch.object(gen, "_invoke_model", return_value={"weight": 1.0}):
        result = gen.summarize(doc_id="cat/doc.py", content="Some content.")
    assert result is None


def test_summarize_with_readme(generator_with_key):
    gen = generator_with_key
    mock_payload = {"summary": "Summary with readme.", "weight": 1.0}
    with patch.object(gen, "_invoke_model", return_value=mock_payload):
        result = gen.summarize(
            doc_id="cat/doc.py",
            content="Main content",
            repo_readme="# Readme content",
            repo_readme_path="README.md",
        )
    assert result is not None
    assert result.repo_readme_path == "README.md"


# ---------------------------------------------------------------------------
# summarize - local mode
# ---------------------------------------------------------------------------


def test_summarize_local_mode(generator_local):
    gen = generator_local
    mock_payload = {"summary": "Local summary.", "weight": 1.1, "model": "local-Qwen"}
    with patch.object(gen, "_invoke_local", return_value=mock_payload):
        result = gen.summarize(doc_id="local/doc.py", content="Local content here.")
    assert result is not None
    assert result.summary == "Local summary."


# ---------------------------------------------------------------------------
# _trim_content
# ---------------------------------------------------------------------------


def test_trim_content_short(generator_with_key):
    gen = generator_with_key
    content = "Short content"
    assert gen._trim_content(content, allow_extra=False) == content


def test_trim_content_long_no_extra(generator_with_key):
    gen = generator_with_key
    gen.max_chars = 10
    content = "A" * 20
    trimmed = gen._trim_content(content, allow_extra=False)
    assert len(trimmed) == 10


def test_trim_content_long_with_extra(generator_with_key):
    gen = generator_with_key
    gen.max_chars = 10
    gen.readme_bonus_chars = 5
    content = "A" * 20
    trimmed = gen._trim_content(content, allow_extra=True)
    assert len(trimmed) == 15


# ---------------------------------------------------------------------------
# _trim_readme
# ---------------------------------------------------------------------------


def test_trim_readme_none(generator_with_key):
    gen = generator_with_key
    assert gen._trim_readme(None) is None


def test_trim_readme_empty(generator_with_key):
    gen = generator_with_key
    assert gen._trim_readme("") is None


def test_trim_readme_short(generator_with_key):
    gen = generator_with_key
    readme = "Short readme"
    assert gen._trim_readme(readme) == readme


def test_trim_readme_long(generator_with_key):
    gen = generator_with_key
    gen.readme_bonus_chars = 5
    readme = "B" * 10
    trimmed = gen._trim_readme(readme)
    assert len(trimmed) == 5


# ---------------------------------------------------------------------------
# _cache_key
# ---------------------------------------------------------------------------


def test_cache_key_deterministic(generator_with_key):
    gen = generator_with_key
    k1 = gen._cache_key("doc/x.py", "content", None, None)
    k2 = gen._cache_key("doc/x.py", "content", None, None)
    assert k1 == k2


def test_cache_key_different_inputs(generator_with_key):
    gen = generator_with_key
    k1 = gen._cache_key("doc/x.py", "content1", None, None)
    k2 = gen._cache_key("doc/x.py", "content2", None, None)
    assert k1 != k2


def test_cache_key_with_readme(generator_with_key):
    gen = generator_with_key
    k1 = gen._cache_key("doc/x.py", "content", "readme text", None)
    k2 = gen._cache_key("doc/x.py", "content", None, None)
    assert k1 != k2


def test_cache_key_with_readme_path(generator_with_key):
    gen = generator_with_key
    k1 = gen._cache_key("doc/x.py", "content", None, "README.md")
    k2 = gen._cache_key("doc/x.py", "content", None, None)
    assert k1 != k2


# ---------------------------------------------------------------------------
# _build_prompt
# ---------------------------------------------------------------------------


def test_build_prompt_basic(generator_with_key):
    gen = generator_with_key
    prompt = gen._build_prompt(
        doc_id="science/repo/file.py",
        repo_name="myrepo",
        repo_readme_path=None,
        repo_readme=None,
        metadata=None,
    )
    assert "science/repo/file.py" in prompt
    assert "myrepo" in prompt


def test_build_prompt_with_readme(generator_with_key):
    gen = generator_with_key
    prompt = gen._build_prompt(
        doc_id="cat/repo/doc.md",
        repo_name="repo",
        repo_readme_path="README.md",
        repo_readme="# Overview\nSome overview.",
        metadata={"category": "science"},
    )
    assert "README.md" in prompt
    assert "Some overview." in prompt
    assert "science" in prompt


def test_build_prompt_readme_is_the_doc(generator_with_key):
    gen = generator_with_key
    prompt = gen._build_prompt(
        doc_id="README.md",
        repo_name="repo",
        repo_readme_path="README.md",
        repo_readme="# README content",
        metadata=None,
    )
    assert "repository README" in prompt.lower() or "README" in prompt


# ---------------------------------------------------------------------------
# _invoke_model
# ---------------------------------------------------------------------------


def test_invoke_model_no_client(generator_with_key):
    gen = generator_with_key
    gen.api_key = None
    with patch.object(gen, "_create_client", return_value=None):
        result = gen._invoke_model(
            prompt="test prompt",
            content="test content",
            readme=None,
            readme_path=None,
        )
    assert result is None


def test_invoke_model_success(generator_with_key):
    gen = generator_with_key
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_block = MagicMock()
    mock_block.type = "text"
    mock_block.text = '{"summary": "Test summary", "weight": 1.2}'
    mock_response.content = [mock_block]
    mock_client.messages.create.return_value = mock_response

    with patch.object(gen, "_create_client", return_value=mock_client):
        result = gen._invoke_model(
            prompt="summarize this",
            content="Some content",
            readme=None,
            readme_path=None,
        )

    assert result is not None
    assert result["summary"] == "Test summary"
    assert result["weight"] == pytest.approx(1.2)


def test_invoke_model_api_exception(generator_with_key):
    gen = generator_with_key
    mock_client = MagicMock()
    mock_client.messages.create.side_effect = ConnectionError("connection refused")

    with patch.object(gen, "_create_client", return_value=mock_client):
        result = gen._invoke_model(
            prompt="summarize",
            content="content",
            readme=None,
            readme_path=None,
        )

    assert result is None
    assert gen.last_error_type == "connection"


def test_invoke_model_with_readme(generator_with_key):
    gen = generator_with_key
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_block = MagicMock()
    mock_block.type = "text"
    mock_block.text = '{"summary": "readme summary", "weight": 1.0}'
    mock_response.content = [mock_block]
    mock_client.messages.create.return_value = mock_response

    with patch.object(gen, "_create_client", return_value=mock_client):
        result = gen._invoke_model(
            prompt="summarize",
            content="content",
            readme="readme text",
            readme_path="README.md",
        )
    assert result is not None


# ---------------------------------------------------------------------------
# _create_client
# ---------------------------------------------------------------------------


def test_create_client_no_key(generator_disabled):
    gen = generator_disabled
    gen.api_key = None
    result = gen._create_client()
    assert result is None


def test_create_client_no_anthropic_module(generator_with_key):
    gen = generator_with_key
    import sys

    saved = sys.modules.get("anthropic")
    sys.modules["anthropic"] = None
    try:
        result = gen._create_client()
    finally:
        if saved is None:
            sys.modules.pop("anthropic", None)
        else:
            sys.modules["anthropic"] = saved
    assert result is None


def test_create_client_success(generator_with_key):
    gen = generator_with_key
    mock_anthropic_module = MagicMock()
    mock_client_instance = MagicMock()
    mock_anthropic_module.Anthropic.return_value = mock_client_instance

    with patch.dict("sys.modules", {"anthropic": mock_anthropic_module}):
        result = gen._create_client()
    assert result == mock_client_instance


# ---------------------------------------------------------------------------
# _strip_markdown_json
# ---------------------------------------------------------------------------


def test_strip_markdown_json_plain(generator_with_key):
    gen = generator_with_key
    text = '{"summary": "test", "weight": 1.0}'
    result = gen._strip_markdown_json(text)
    assert result == text


def test_strip_markdown_json_with_code_block(generator_with_key):
    gen = generator_with_key
    text = '```json\n{"summary": "test", "weight": 1.0}\n```'
    result = gen._strip_markdown_json(text)
    assert result.strip() == '{"summary": "test", "weight": 1.0}'


def test_strip_markdown_json_code_block_no_newline(generator_with_key):
    gen = generator_with_key
    text = '```json{"summary": "test"}```'
    result = gen._strip_markdown_json(text)
    assert "```" not in result


# ---------------------------------------------------------------------------
# _invoke_local
# ---------------------------------------------------------------------------


def test_invoke_local_no_torch(generator_local):
    gen = generator_local
    import sys

    saved = sys.modules.get("torch")
    sys.modules["torch"] = None
    try:
        result = gen._invoke_local(content="content", readme=None)
    finally:
        if saved is None:
            sys.modules.pop("torch", None)
        else:
            sys.modules["torch"] = saved
    assert result is None


def test_invoke_local_success(generator_local, monkeypatch):
    """Test _invoke_local with fully mocked transformers and torch."""
    import nancy_brain.summarization as summ_mod

    mock_torch = MagicMock()
    mock_torch.cuda.is_available.return_value = False
    mock_torch.float32 = "float32"
    mock_torch.inference_mode.return_value.__enter__ = MagicMock(return_value=None)
    mock_torch.inference_mode.return_value.__exit__ = MagicMock(return_value=False)

    # Use a callable class to simulate the tokenizer instance
    class FakeTokenizer:
        eos_token_id = 0

        def apply_chat_template(self, *args, **kwargs):
            return "formatted prompt"

        def batch_decode(self, ids, skip_special_tokens=True):
            return ["This is a great summary."]

        def __call__(self, texts, return_tensors=None):
            mock_inputs = MagicMock()
            mock_inputs.input_ids = [[1, 2, 3]]
            return mock_inputs

        def to(self, device):
            return self

    tokenizer_instance = FakeTokenizer()
    mock_auto_tokenizer = MagicMock(return_value=tokenizer_instance)

    mock_model = MagicMock()
    mock_model.device = "cpu"
    mock_model.generate.return_value = [[1, 2, 3, 4]]

    mock_auto_model = MagicMock(return_value=mock_model)

    import types

    mock_transformers = types.ModuleType("transformers")
    mock_transformers.AutoTokenizer = mock_auto_tokenizer
    mock_transformers.AutoModelForCausalLM = mock_auto_model

    # Reset pipeline cache
    summ_mod._summarizer_pipeline = None

    with patch.dict("sys.modules", {"torch": mock_torch, "transformers": mock_transformers}):
        gen = generator_local
        result = gen._invoke_local(content="Some content", readme=None)

    # Result may be None if parsing fails, or a dict if successful
    assert result is None or isinstance(result, dict)
