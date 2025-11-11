"""
RAG (Retrieval-Augmented Generation) service for the Slack bot.
Provides semantic search capabilities using txtai embeddings.
"""

# imports
import logging
from typing import Optional
from .service import RAGService

logger = logging.getLogger(__name__)

__version__ = "0.1.9"

# Global instance for the bot to use
rag_service = None


def get_rag_service() -> Optional[RAGService]:
    """Get the global RAG service instance."""
    global rag_service
    if rag_service is None:
        rag_service = RAGService()
    return rag_service
