#!/usr/bin/env python3
"""
PDF Processing Utilities for Nancy's Knowledge Base

This module provides reliable PDF text extraction using Tika with proper initialization.
"""

import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)


def initialize_tika():
    """Initialize Tika VM properly for PDF processing"""
    try:
        import warnings

        with warnings.catch_warnings():
            warnings.filterwarnings(
                "ignore",
                category=UserWarning,
                message=r"pkg_resources is deprecated as an API.*",
            )
            import tika

        tika.initVM()
        logger.info("✅ Tika VM initialized successfully")
        return True
    except Exception as e:
        logger.error(f"❌ Failed to initialize Tika VM: {e}")
        return False


def extract_pdf_text(pdf_path: str) -> Optional[str]:
    """
    Extract text from a PDF file using Tika

    Args:
        pdf_path: Path to the PDF file

    Returns:
        Extracted text content or None if extraction failed
    """
    try:
        import warnings

        with warnings.catch_warnings():
            warnings.filterwarnings(
                "ignore",
                category=UserWarning,
                message=r"pkg_resources is deprecated as an API.*",
            )
            from tika import parser

        logger.info(f"Extracting text from {pdf_path}...")
        parsed = parser.from_file(pdf_path)

        if parsed and "content" in parsed and parsed["content"]:
            content = parsed["content"]
            logger.info(f"✅ Extracted {len(content)} characters from PDF")
            return content.strip()
        else:
            logger.warning(f"⚠️  No content extracted from {pdf_path}")
            return None

    except Exception as e:
        logger.error(f"❌ Error extracting text from {pdf_path}: {e}")
        return None


def test_pdf_extraction(pdf_path: str) -> bool:
    """Test PDF extraction on a single file"""
    if not os.path.exists(pdf_path):
        logger.error(f"PDF file not found: {pdf_path}")
        return False

    # Initialize Tika
    if not initialize_tika():
        return False

    # Extract text
    content = extract_pdf_text(pdf_path)
    if content:
        logger.info("✅ PDF extraction test successful")
        logger.info(f"📄 Content preview: {content[:200]}...")
        return True
    else:
        logger.error("❌ PDF extraction test failed")
        return False


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        test_pdf_extraction(sys.argv[1])
    else:
        print("Usage: python pdf_utils.py <path_to_pdf>")
