import os
import pytest
from pathlib import Path
from dotenv import load_dotenv
from nancy_brain.summarization import SummaryGenerator


@pytest.mark.integration
def test_llm_summary_json_and_weight():
    """
    Integration test: Assert that SummaryGenerator returns valid JSON and float weight from real LLM call.
    """
    # Load environment variables
    load_dotenv("config/.env")
    api_key = os.environ.get("GEMINI_API_KEY")
    assert api_key, "GEMINI_API_KEY must be set in environment or .env file"

    cache_dir = Path("./test_llm_cache")
    summary_gen = SummaryGenerator(cache_dir=cache_dir, enabled=True)

    # Use a small, representative file for speed
    test_file = Path("nancy_brain/summarization.py")
    assert test_file.exists(), f"Test file {test_file} does not exist"
    content = test_file.read_text(encoding="utf-8")

    result = summary_gen.summarize(
        doc_id="nancy-brain/nancy_brain/summarization.py",
        content=content,
        repo_name="nancy-brain",
        metadata={"file_type": ".py"},
    )
    assert result is not None, "LLM did not return a result"

    # Assert JSON structure
    assert hasattr(result, "summary"), "Result missing 'summary' field"
    assert hasattr(result, "weight"), "Result missing 'weight' field"
    assert isinstance(result.summary, str), "Summary is not a string"
    assert isinstance(result.weight, float), "Weight is not a float"
    assert 0.5 <= result.weight <= 2.0, f"Weight {result.weight} out of expected range [0.5, 2.0]"
    assert len(result.summary) > 50, "Summary too short to be meaningful"

    print(f"LLM summary: {result.summary[:100]}...")
    print(f"LLM weight: {result.weight}")
