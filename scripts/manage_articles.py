#!/usr/bin/env python3
"""
Article Management Script for Nancy's Knowledge Base

This script helps manage journal articles (PDFs) for Nancy's microlensing knowledge base.
It can process PDF files, extract text, and add them to the embeddings database.

Requirements:
- Optional OCR extras: pip install nancy-brain[ocr] or nancy-brain[ocr-gpu]

Usage:
    python scripts/manage_articles.py add /path/to/article.pdf
    python scripts/manage_articles.py add-directory /path/to/articles/
    python scripts/manage_articles.py list
    python scripts/manage_articles.py remove "article_id"
    python scripts/manage_articles.py rebuild
"""

import os

# Fix OpenMP issue before importing any ML libraries
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

import argparse
import sys
import time
from pathlib import Path
from typing import List, Dict, Optional

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from rag_core.service import RAGService
from nancy_brain.pdf_ocr import PDFOCRResult, extract_pdf_markdown, get_pdf_ocr_backend_status

TXTAI_AVAILABLE = True


class Textractor:
    """Compatibility wrapper that now delegates PDF extraction to the OCR pipeline."""

    def __init__(self, *args, cache_dir: Optional[Path] = None, **kwargs):
        self.cache_dir = Path(cache_dir) if cache_dir is not None else None
        self.last_result = None

    def __call__(self, pdf_path: str | Path) -> str:
        self.last_result = extract_pdf_markdown(pdf_path, cache_dir=self.cache_dir)
        return self.last_result.markdown or ""


class ArticleManager:
    """Manages journal articles in Nancy's knowledge base"""

    def __init__(self, knowledge_base_path: Optional[Path] = None):
        """
        Initialize the article manager

        Args:
            knowledge_base_path: Path to knowledge base, defaults to project knowledge_base/
        """
        if knowledge_base_path is None:
            knowledge_base_path = project_root / "knowledge_base"

        self.knowledge_base_path = knowledge_base_path
        self.articles_path = knowledge_base_path / "raw" / "journal_articles"
        self.articles_path.mkdir(parents=True, exist_ok=True)
        self.pdf_ocr_cache_dir = self.knowledge_base_path / "cache" / "pdf_ocr"

        # Initialize RAG service
        self.rag = RAGService()

        self.textractor = Textractor(cache_dir=self.pdf_ocr_cache_dir)
        backend_status = get_pdf_ocr_backend_status()
        if backend_status.available:
            print(f"✅ PDF OCR backend ready: {backend_status.name} ({backend_status.model})")
        else:
            print(f"⚠️  PDF OCR backend unavailable: {backend_status.reason}")

    def add_article(self, pdf_path: Path, article_id: Optional[str] = None) -> bool:
        """
        Add a journal article PDF to the knowledge base

        Args:
            pdf_path: Path to the PDF file
            article_id: Optional custom ID, defaults to filename without extension

        Returns:
            True if successful, False otherwise
        """
        try:
            pdf_path = Path(pdf_path)
            if not pdf_path.exists():
                print(f"❌ File not found: {pdf_path}")
                return False

            if pdf_path.suffix.lower() != ".pdf":
                print(f"❌ Not a PDF file: {pdf_path}")
                return False

            # Generate article ID if not provided
            if article_id is None:
                article_id = f"journal_articles/{pdf_path.stem}"

            print(f"📄 Processing PDF: {pdf_path.name}")
            print(f"🆔 Article ID: {article_id}")

            # Extract text from PDF
            print("🔄 Extracting text from PDF...")
            try:
                text_content = self.textractor(str(pdf_path))
                ocr_result = getattr(self.textractor, "last_result", None)
                if not isinstance(ocr_result, PDFOCRResult):
                    ocr_result = None
                text_content = text_content.strip()
                if ocr_result is not None and ocr_result.warning:
                    print(f"⚠️  OCR note: {ocr_result.warning}")
                if not text_content or len(text_content.strip()) < 100:
                    print("❌ Failed to extract meaningful text from PDF")
                    return False
                if ocr_result is not None:
                    cache_state = "hit" if ocr_result.cached else "miss"
                    print(f"✅ Extracted {len(text_content)} characters with {ocr_result.backend} OCR ({cache_state})")
                else:
                    print(f"✅ Extracted {len(text_content)} characters")
            except Exception as e:
                print(f"❌ Error extracting text: {e}")
                return False

            # Copy PDF to articles directory
            dest_path = self.articles_path / pdf_path.name
            if dest_path.exists():
                print(f"⚠️  Article already exists at {dest_path}")
                if not self._confirm("Overwrite existing file?"):
                    return False

            print(f"📁 Copying PDF to {dest_path}")
            import shutil

            shutil.copy2(pdf_path, dest_path)

            # Add to embeddings database
            print("🔄 Adding to embeddings database...")
            try:
                # Create document entry
                document = {
                    "id": article_id,
                    "text": text_content,
                    "source": "journal_article",
                    "file_path": str(dest_path.relative_to(project_root)),
                    "original_name": pdf_path.name,
                    "added_date": time.strftime("%Y-%m-%d %H:%M:%S"),
                }

                # Index the document
                self.rag.embeddings.index([(article_id, document, None)])
                print(f"✅ Added article to knowledge base: {article_id}")
                return True

            except Exception as e:
                print(f"❌ Error adding to database: {e}")
                # Clean up copied file on failure
                if dest_path.exists():
                    dest_path.unlink()
                return False

        except Exception as e:
            print(f"❌ Unexpected error: {e}")
            return False

    def add_directory(self, directory_path: Path) -> int:
        """
        Add all PDF files from a directory

        Args:
            directory_path: Directory containing PDF files

        Returns:
            Number of successfully processed files
        """
        directory_path = Path(directory_path)
        if not directory_path.exists():
            print(f"❌ Directory not found: {directory_path}")
            return 0

        pdf_files = list(directory_path.glob("*.pdf"))
        if not pdf_files:
            print(f"❌ No PDF files found in {directory_path}")
            return 0

        print(f"📚 Found {len(pdf_files)} PDF files in {directory_path}")

        successful = 0
        for pdf_file in pdf_files:
            print(f"\n--- Processing {pdf_file.name} ---")
            if self.add_article(pdf_file):
                successful += 1
            else:
                print(f"❌ Failed to process {pdf_file.name}")

        print(f"\n✅ Successfully processed {successful}/{len(pdf_files)} articles")
        return successful

    def list_articles(self) -> List[Dict]:
        """
        List all journal articles in the knowledge base

        Returns:
            List of article information dictionaries
        """
        try:
            # Query for journal articles
            results = list(
                self.rag.embeddings.database.search("SELECT id, text FROM txtai WHERE id LIKE 'journal_articles/%'")
            )

            articles = []
            for result in results:
                article_id = result["id"]
                # Try to get metadata from the text (first few lines often contain title info)
                text_preview = result["text"][:200] + "..." if len(result["text"]) > 200 else result["text"]

                articles.append(
                    {
                        "id": article_id,
                        "preview": text_preview,
                        "length": len(result["text"]),
                    }
                )

            return articles

        except Exception as e:
            print(f"❌ Error listing articles: {e}")
            return []

    def remove_article(self, article_id: str) -> bool:
        """
        Remove an article from the knowledge base

        Args:
            article_id: ID of the article to remove

        Returns:
            True if successful, False otherwise
        """
        try:
            # Check if article exists
            results = list(self.rag.embeddings.database.search(f"SELECT id FROM txtai WHERE id = '{article_id}'"))

            if not results:
                print(f"❌ Article not found: {article_id}")
                return False

            # Remove from database
            self.rag.embeddings.delete([article_id])

            # Try to remove physical file if it exists
            try:
                filename = article_id.split("/")[-1] + ".pdf"
                file_path = self.articles_path / filename
                if file_path.exists():
                    file_path.unlink()
                    print(f"🗑️  Removed file: {file_path}")
            except Exception as e:
                print(f"⚠️  Could not remove physical file: {e}")

            print(f"✅ Removed article: {article_id}")
            return True

        except Exception as e:
            print(f"❌ Error removing article: {e}")
            return False

    def rebuild_index(self) -> bool:
        """
        Rebuild the embeddings index including all articles

        Returns:
            True if successful, False otherwise
        """
        try:
            print("🔄 Rebuilding embeddings index...")
            # This would trigger a full rebuild of the knowledge base
            print("⚠️  This feature requires implementation in the RAG service")
            print("💡 Consider running the build_knowledge_base.py script instead")
            return False

        except Exception as e:
            print(f"❌ Error rebuilding index: {e}")
            return False

    def _confirm(self, message: str) -> bool:
        """Ask user for confirmation"""
        response = input(f"{message} (y/N): ").strip().lower()
        return response in ["y", "yes"]


def main():
    """Main CLI interface"""
    parser = argparse.ArgumentParser(
        description="Manage journal articles in Nancy's knowledge base",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s add /path/to/article.pdf
  %(prog)s add /path/to/article.pdf --id "custom_article_id"
  %(prog)s add-directory /path/to/articles/
  %(prog)s list
  %(prog)s remove "journal_articles/article_name"
        """,
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Add article command
    add_parser = subparsers.add_parser("add", help="Add a single PDF article")
    add_parser.add_argument("pdf_path", help="Path to the PDF file")
    add_parser.add_argument("--id", dest="article_id", help="Custom article ID")

    # Add directory command
    dir_parser = subparsers.add_parser("add-directory", help="Add all PDFs from a directory")
    dir_parser.add_argument("directory_path", help="Directory containing PDF files")

    # List articles command
    list_parser = subparsers.add_parser("list", help="List all articles in knowledge base")

    # Remove article command
    remove_parser = subparsers.add_parser("remove", help="Remove an article from knowledge base")
    remove_parser.add_argument("article_id", help="ID of the article to remove")

    # Rebuild index command
    rebuild_parser = subparsers.add_parser("rebuild", help="Rebuild the embeddings index")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    # Initialize article manager
    try:
        manager = ArticleManager()
    except Exception as e:
        print(f"❌ Failed to initialize article manager: {e}")
        return

    # Execute commands
    if args.command == "add":
        success = manager.add_article(Path(args.pdf_path), args.article_id)
        sys.exit(0 if success else 1)

    elif args.command == "add-directory":
        count = manager.add_directory(Path(args.directory_path))
        sys.exit(0 if count > 0 else 1)

    elif args.command == "list":
        articles = manager.list_articles()
        if articles:
            print(f"\n📚 Found {len(articles)} journal articles:")
            print("-" * 80)
            for article in articles:
                print(f"🆔 ID: {article['id']}")
                print(f"📄 Length: {article['length']:,} characters")
                print(f"🔍 Preview: {article['preview']}")
                print("-" * 80)
        else:
            print("📭 No journal articles found in knowledge base")

    elif args.command == "remove":
        success = manager.remove_article(args.article_id)
        sys.exit(0 if success else 1)

    elif args.command == "rebuild":
        success = manager.rebuild_index()
        sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
