#!/usr/bin/env python3
"""Test script using the correct google-genai package."""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from config/.env
load_dotenv("config/.env")


def test_new_gemini_api():
    """Test the new google-genai package."""

    # Check if GEMINI_API_KEY is set
    if not os.environ.get("GEMINI_API_KEY"):
        print("ERROR: GEMINI_API_KEY environment variable not set")
        return

    print(f"Using API key: {os.environ.get('GEMINI_API_KEY')[:10]}...")

    try:
        from google import genai

        # Create client (automatically picks up GEMINI_API_KEY)
        client = genai.Client()

        print("Testing simple request...")
        response = client.models.generate_content(
            model="gemini-2.5-flash", contents="Say 'Hello, this is a test of the new API'"
        )
        print(f"SUCCESS: {response.text}")
        print("=" * 60)

        # Now test with JSON response
        print("Testing JSON response...")
        response = client.models.generate_content(
            model="gemini-2.5-flash", contents="Respond with JSON: {'message': 'Hello', 'status': 'success'}"
        )
        print(f"JSON Response: {response.text}")
        print("=" * 60)

        # Test with a document summary task
        print("Testing document summary...")
        test_content = """
        This is a Python script that implements a knowledge base builder.
        It processes documents, chunks them, and creates embeddings for search.
        The script supports batch processing and incremental indexing.
        """

        prompt = (
            """
        Summarize this document and respond with JSON in this format:
        {"summary": "brief summary", "weight": float_between_0.5_and_2.0}
        
        Document:
        """  # Noqa: W293
            + test_content
        )  # Noqa: W293

        response = client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
        print(f"Summary Response: {response.text}")

    except Exception as e:
        print(f"ERROR: {e}")
        import traceback

        traceback.print_exc()


def test_readme_summary():
    """Test summarizing the actual README file."""

    readme_path = Path("README.md")
    if not readme_path.exists():
        print("README.md not found")
        return

    content = readme_path.read_text(encoding="utf-8")
    print(f"README.md size: {len(content)} characters")

    try:
        from google import genai

        client = genai.Client()

        # Truncate content to avoid hitting limits
        truncated_content = content[:20000] if len(content) > 20000 else content

        prompt = f"""
        You are Nancy Brain's knowledge-base summarizer.
        Summarize the provided repository file in clear English.
        Summaries should be concise yet informative (up to ~400 words), focusing on key functionality and purpose.
        Respond with JSON using keys: summary (string), weight (float in [0.5, 2.0]).
        Weight reflects relative usefulness for retrieval (1.0 = neutral).
        Consider scientific relevance, implementation depth, uniqueness, and clarity.
        
        Summarize document: README.md
        
        Full document:
        {truncated_content}
        """  # Noqa: W293

        response = client.models.generate_content(model="gemini-2.5-flash", contents=prompt)

        print("README SUMMARY RESULT:")
        print(response.text)

        # Try to parse as JSON, stripping markdown code blocks if present
        import json

        raw_text = response.text.strip()
        print(f"Raw response length: {len(raw_text)}")

        # Simple string stripping approach
        json_text = raw_text
        if raw_text.startswith("```json"):
            json_text = json_text[7:]  # Remove "```json"
            if json_text.startswith("\n"):
                json_text = json_text[1:]  # Remove leading newline
        if json_text.endswith("```"):
            json_text = json_text[:-3]  # Remove trailing "```"
            if json_text.endswith("\n"):
                json_text = json_text[:-1]  # Remove trailing newline

        print(f"Cleaned text length: {len(json_text)}")

        try:
            parsed = json.loads(json_text)
            print("\nParsed successfully:")
            print(f"Summary: {parsed.get('summary', 'N/A')}")
            print(f"Weight: {parsed.get('weight', 'N/A')}")
        except json.JSONDecodeError as e:
            print(f"JSON parsing failed: {e}")
            print(f"Attempted to parse: {json_text[:200]}...")

    except Exception as e:
        print(f"ERROR during README summary: {e}")
        import traceback

        traceback.print_exc()


if __name__ == "__main__":
    print("Testing new google-genai package...")
    test_new_gemini_api()
    print("\n" + "=" * 80 + "\n")
    print("Testing README summary...")
    test_readme_summary()
