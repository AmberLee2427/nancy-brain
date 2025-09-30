#!/usr/bin/env python3
"""Test the real SummaryGenerator in a KB pipeline simulation."""

import os
import sys
from pathlib import Path
from dotenv import load_dotenv

# Add the project root to Python path
sys.path.insert(0, str(Path(__file__).parent))

# Load environment variables from config/.env
load_dotenv("config/.env")

from nancy_brain.summarization import SummaryGenerator


def test_real_summary_generator():
    """Test the actual SummaryGenerator class used in build_knowledge_base.py"""

    # Check if GEMINI_API_KEY is set
    if not os.environ.get("GEMINI_API_KEY"):
        print("ERROR: GEMINI_API_KEY environment variable not set")
        return

    print("Testing real SummaryGenerator class...")
    print(f"Using API key: {os.environ.get('GEMINI_API_KEY')[:10]}...")
    print("=" * 60)

    # Create cache directory like the real build process
    cache_dir = Path("./test_summary_cache")

    # Initialize SummaryGenerator exactly like build_knowledge_base.py does
    summary_gen = SummaryGenerator(cache_dir=cache_dir, enabled=True)

    print(f"SummaryGenerator enabled: {summary_gen.enabled}")
    print(f"Model: {summary_gen.model_name}")
    print(f"Max chars: {summary_gen.max_chars}")
    print("=" * 60)

    # Test files to simulate KB pipeline
    test_files = [
        {"path": "README.md", "doc_id": "nancy-brain/README.md", "repo_name": "nancy-brain"},
        {
            "path": "nancy_brain/summarization.py",
            "doc_id": "nancy-brain/nancy_brain/summarization.py",
            "repo_name": "nancy-brain",
        },
    ]

    results = []

    for test_file in test_files:
        file_path = Path(test_file["path"])
        if not file_path.exists():
            print(f"Skipping {test_file['path']} - file not found")
            continue

        content = file_path.read_text(encoding="utf-8")
        print(f"\nTesting: {test_file['path']}")
        print(f"Content length: {len(content)} characters")

        try:
            # Call summarize exactly like build_knowledge_base.py does
            result = summary_gen.summarize(
                doc_id=test_file["doc_id"],
                content=content,
                repo_name=test_file["repo_name"],
                metadata={"file_type": file_path.suffix},
            )

            if result:
                print("✅ SUCCESS:")
                print(f"   Summary: {result.summary[:100]}...")
                print(f"   Weight: {result.weight}")
                print(f"   Model: {result.model}")
                print(f"   Cached: {result.cached}")
                results.append(
                    {
                        "file": test_file["path"],
                        "success": True,
                        "summary_length": len(result.summary),
                        "weight": result.weight,
                    }
                )
            else:
                print("❌ FAILED: No result returned")
                results.append({"file": test_file["path"], "success": False})

        except Exception as e:
            print(f"❌ ERROR: {e}")
            results.append({"file": test_file["path"], "success": False, "error": str(e)})

    # Summary report
    print("\n" + "=" * 80)
    print("SUMMARY REPORT:")
    print("=" * 80)

    successful = [r for r in results if r.get("success")]
    failed = [r for r in results if not r.get("success")]

    print(f"✅ Successful: {len(successful)}")
    print(f"❌ Failed: {len(failed)}")

    if successful:
        print("\nSuccessful summaries:")
        for result in successful:
            print(f"  - {result['file']}: {result['summary_length']} chars, weight {result['weight']}")

    if failed:
        print("\nFailed summaries:")
        for result in failed:
            error_msg = result.get("error", "No result returned")
            print(f"  - {result['file']}: {error_msg}")

    print(f"\nCache directory: {cache_dir}")
    if cache_dir.exists():
        cache_files = list(cache_dir.glob("*.json"))
        print(f"Cache files created: {len(cache_files)}")


def test_with_readme_context():
    """Test summarization with README context like the real pipeline."""

    print("\n" + "=" * 80)
    print("TESTING WITH README CONTEXT (like real pipeline)")
    print("=" * 80)

    cache_dir = Path("./test_summary_cache")
    summary_gen = SummaryGenerator(cache_dir=cache_dir, enabled=True)

    # Read README for context
    readme_path = Path("README.md")
    if not readme_path.exists():
        print("README.md not found, skipping context test")
        return

    readme_content = readme_path.read_text(encoding="utf-8")

    # Test summarizing a code file with README context
    code_file = Path("nancy_brain/cli.py")
    if not code_file.exists():
        print("CLI file not found, skipping context test")
        return

    code_content = code_file.read_text(encoding="utf-8")

    print(f"Summarizing {code_file} with README context...")
    print(f"Code file: {len(code_content)} chars")
    print(f"README context: {len(readme_content)} chars")

    try:
        result = summary_gen.summarize(
            doc_id="nancy-brain/nancy_brain/cli.py",
            content=code_content,
            repo_name="nancy-brain",
            repo_readme=readme_content,
            repo_readme_path="README.md",
            metadata={"file_type": ".py", "component": "cli"},
        )

        if result:
            print("✅ SUCCESS with README context:")
            print(f"   Summary: {result.summary}")
            print(f"   Weight: {result.weight}")
            print(f"   README path: {result.repo_readme_path}")
        else:
            print("❌ FAILED: No result with README context")

    except Exception as e:
        print(f"❌ ERROR with README context: {e}")


if __name__ == "__main__":
    test_real_summary_generator()
    test_with_readme_context()
