"""HTTP API connector for Nancy RAG core."""

from .app import app, initialize_rag_service

__all__ = ["app", "initialize_rag_service"]
