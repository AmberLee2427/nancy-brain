#!/usr/bin/env python3
"""Quick test script to see what SummaryGenerator returns from Gemini."""

import logging
import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Add the project root to Python path
sys.path.insert(0, str(Path(__file__).parent))

# Load environment variables from config/.env
load_dotenv("config/.env")

from nancy_brain.summarization import SummaryGenerator

# Set up detailed logging
logging.basicConfig(level=logging.DEBUG, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")


def list_available_models():
    """List available Gemini models."""
    try:
        import google.generativeai as genai

        genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))

        print("Available models:")
        for model in genai.list_models():
            print(f"  - {model.name}")
    except Exception as e:
        print(f"Error listing models: {e}")


def test_summary_on_file(file_path: str):
    """Test summarization on a specific file and log everything."""

    # Check if GEMINI_API_KEY is set
    if not os.environ.get("GEMINI_API_KEY"):
        print("ERROR: GEMINI_API_KEY environment variable not set")
        return

    # First, list available models
    list_available_models()
    print("=" * 60)

    # Read the target file
    target_file = Path(file_path)
    if not target_file.exists():
        print(f"ERROR: File {file_path} does not exist")
        return

    content = target_file.read_text(encoding="utf-8")
    print(f"Testing summarization on: {file_path}")
    print(f"File size: {len(content)} characters")
    print("=" * 60)

    # Create cache directory
    cache_dir = Path("./test_summary_cache")

    # Initialize SummaryGenerator with correct model name
    summary_gen = SummaryGenerator(
        cache_dir=cache_dir,
        enabled=True,
        model_name="models/gemini-1.5-flash",  # Use the correct model name with prefix
    )

    print(f"SummaryGenerator enabled: {summary_gen.enabled}")
    print(f"Model: {summary_gen.model_name}")
    print(f"Max chars: {summary_gen.max_chars}")
    print("=" * 60)

    # Call summarize and log everything
    print("Calling summarize()...")
    try:
        # Let's try calling the Gemini API directly first
        import google.generativeai as genai

        genai.configure(api_key=os.environ.get("GEMINI_API_KEY"))

        print("Testing direct Gemini API call...")

        # Try different model name formats
        try:
            print("Trying 'gemini-1.5-flash' (no models/ prefix)...")
            model = genai.GenerativeModel("gemini-1.5-flash")
            test_response = model.generate_content("Say 'Hello, this is a test'")
            print(f"SUCCESS: {test_response.text}")
        except Exception as e:
            print(f"Failed: {e}")

        try:
            print("Trying 'models/gemini-1.5-flash' (with models/ prefix)...")
            model = genai.GenerativeModel("models/gemini-1.5-flash")
            test_response = model.generate_content("Say 'Hello, this is a test'")
            print(f"SUCCESS: {test_response.text}")
        except Exception as e:
            print(f"Failed: {e}")

        print("=" * 40)

        result = summary_gen.summarize(
            doc_id=file_path, content=content, repo_name="nancy-brain", metadata={"file_type": target_file.suffix}
        )

        print("RAW RESULT:")
        print(f"Type: {type(result)}")
        if result:
            print(f"Summary: {result.summary}")
            print(f"Weight: {result.weight}")
            print(f"Model: {result.model}")
            print(f"Cached: {result.cached}")
            print(f"Repo readme path: {result.repo_readme_path}")
        else:
            print("Result is None")

    except Exception as e:
        print(f"ERROR during summarization: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    # Test on the README file as a good example
    test_file = "README.md"
    if len(sys.argv) > 1:
        test_file = sys.argv[1]

    test_summary_on_file(test_file)
