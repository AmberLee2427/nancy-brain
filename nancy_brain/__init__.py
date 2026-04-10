"""Nancy Brain - Turn GitHub repos into AI-searchable knowledge bases."""

__version__ = "0.2.1"

__all__ = ["cli", "RAGService", "__version__"]


def __getattr__(name):
    """Lazily expose heavyweight package attributes.

    Importing `nancy_brain` should stay cheap so isolated OCR worker runtimes
    can import `nancy_brain.pdf_ocr` without also needing CLI or full RAG deps.
    """

    if name == "cli":
        from .cli import cli

        return cli

    if name == "RAGService":
        try:
            import sys
            from pathlib import Path

            # Add parent directory to path to import rag_core
            sys.path.insert(0, str(Path(__file__).parent.parent))
            from rag_core.service import RAGService

            return RAGService
        except ImportError:
            return None

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
