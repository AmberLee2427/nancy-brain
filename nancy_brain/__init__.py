"""Nancy Brain - Turn GitHub repos into AI-searchable knowledge bases."""

__version__ = "0.1.8"

from .cli import cli

# Re-export main components for easy importing
try:
    import sys
    from pathlib import Path

    # Add parent directory to path to import rag_core
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from rag_core.service import RAGService
except ImportError:
    # Graceful fallback if dependencies aren't installed
    RAGService = None

__all__ = ["cli", "RAGService", "__version__"]
