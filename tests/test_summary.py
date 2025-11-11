import os
from pathlib import Path

import pytest
from dotenv import load_dotenv

from nancy_brain.summarization import SummaryGenerator


load_dotenv("config/.env")


@pytest.mark.integration
def test_summary_on_readme(tmp_path):
    """Ensure SummaryGenerator can produce a summary when ANTHROPIC_API_KEY is available."""

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        pytest.skip("ANTHROPIC_API_KEY not configured")

    readme_path = Path("README.md")
    if not readme_path.exists():
        pytest.skip("README.md not present in repository")

    content = readme_path.read_text(encoding="utf-8")
    assert content.strip(), "README.md is empty"

    cache_dir = tmp_path / "summary_cache"
    summary_gen = SummaryGenerator(cache_dir=cache_dir, enabled=True)

    result = summary_gen.summarize(
        doc_id="README.md",
        content=content,
        repo_name="nancy-brain",
        metadata={"file_type": ".md"},
    )
    assert result is not None, "Summarizer returned no result"
    assert isinstance(result.summary, str) and result.summary.strip(), "Summary text missing"
    assert isinstance(result.weight, float), "Summary weight missing"
    assert 0.5 <= result.weight <= 2.0, "Summary weight out of expected range"
