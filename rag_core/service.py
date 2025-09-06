""" """

# import
from typing import List, Dict, Optional
import os
import logging
from pathlib import Path
from .store import Store
from .registry import Registry, ModelWeights

logger = logging.getLogger(__name__)


class RAGService:
    """RAG service for retrieving relevant context from the knowledge base."""

    def __init__(
        self,
        embeddings_path: Path,
        config_path: Path,
        weights_path: Path,
        use_dual_embedding: Optional[bool] = None,
        search_instance: Optional[object] = None,
    ):
        """
        Initialize the RAG service.

        Args:
            embeddings_path: Path to the txtai embeddings index
            config_path: Path to the repositories configuration file
            weights_path: Path to the model weights file
            use_dual_embedding: Whether to use dual embedding models (general + code).
                               If None, reads from USE_DUAL_EMBEDDING environment variable.
        """
        # Read dual embedding setting from environment if not explicitly set
        if use_dual_embedding is None:
            use_dual_embedding = os.environ.get("USE_DUAL_EMBEDDING", "true").lower() == "true"

        # Initialize core components
        self.registry = Registry(config_path, use_dual_embedding=use_dual_embedding)
        self.store = Store(embeddings_path.parent)
        # Defer loading of Search (and heavy txtai/torch imports) until actually needed.
        # Store parameters for lazy initialization. Allow an injected search instance
        # (used in tests or by DI) to bypass lazy loading.
        self._search_args = {
            "embeddings_path": embeddings_path,
            "dual": use_dual_embedding,
            "code_model": os.environ.get("CODE_EMBEDDING_MODEL", "microsoft/codebert-base"),
        }
        # Allow injection for testing / DI. If an explicit search_instance is
        # provided, use it. Otherwise prefer lazy-loading. However, many
        # existing tests assume a lightweight placeholder is present when an
        # embeddings index is not initialized. To keep both behaviours:
        # - If the embeddings index directory exists, start with `self.search`
        #   as None (true lazy init).
        # - If the index does NOT exist, provide a lightweight Placeholder
        #   so tests can set `service.search.search = Mock(...)` without
        #   pulling heavy dependencies.
        if search_instance is not None:
            self.search = search_instance
        else:
            # If rag_core.search was explicitly removed (e.g. tests set
            # sys.modules['rag_core.search'] = None) treat as missing and
            # keep search as None to surface that txtai isn't available.
            module_entry = None
            try:
                module_entry = __import__("sys").modules.get("rag_core.search", None)
            except Exception:
                module_entry = None

            index_dir = Path(embeddings_path) / "index"
            index_exists = index_dir.exists()

            if module_entry is None and "rag_core.search" in __import__("sys").modules:
                # Explicitly set to None in sys.modules -> behave as missing
                self.search = None
            elif index_exists:
                # If an index is present prefer true lazy-loading (None)
                self.search = None
            else:
                # Lightweight placeholder Search that defers to general_embeddings if present.
                class PlaceholderSearch:
                    def __init__(self):
                        self.general_embeddings = None
                        self.model_weights = {}
                        self.extension_weights = {}

                    def search(self, query, limit):
                        if self.general_embeddings is not None and hasattr(self.general_embeddings, "search"):
                            return self.general_embeddings.search(query, limit)
                        return []

                self.search = PlaceholderSearch()

        # Mirror legacy attribute for tests that check service.general_embeddings
        # Keep synced with the placeholder if present
        self.general_embeddings = getattr(self.search, "general_embeddings", None)
        self.weights = ModelWeights(weights_path)

        # Store paths
        self.embeddings_path = embeddings_path
        self.config_path = config_path
        self.weights_path = weights_path
        self.use_dual_embedding = use_dual_embedding

        self._weights = {}  # runtime weights set via API

    def _ensure_search_loaded(self):
        """Lazily initialize the Search instance to avoid importing heavy
        dependencies (txtai/torch) at module import or during CLI help/tests.
        """
        if getattr(self, "search", None) is not None:
            return

        try:
            # Import here to keep heavy imports local
            Search = None
            try:
                from .search import Search as _Search

                Search = _Search
            except Exception:
                Search = None

            if Search is None:
                self.search = None
                return

            args = self._search_args or {}
            try:
                self.search = Search(
                    args.get("embeddings_path"),
                    dual=args.get("dual", False),
                    code_model=args.get("code_model"),
                )
            except Exception:
                # If Search initialization fails (e.g., txtai import error), leave as None
                self.search = None
        except Exception:
            self.search = None
        # Sync general_embeddings mirror if search instance provided
        try:
            self.general_embeddings = getattr(self.search, "general_embeddings", None)
        except Exception:
            self.general_embeddings = None

    """
    def search(self, query, limit):
        hits = self.search.run(query, limit)
        # apply weights via self.weights then return
    def retrieve(self, doc_id, start, end):
        meta = self.registry.get_meta(doc_id)
        text = self.store.read_lines(doc_id, start, end)
        return Passage(doc_id, text, meta.github_url, meta.content_sha256)
    # list_tree, set_weight, version() similarly thin"""

    def get_context_for_query(self, query: str, max_chars: int = 4000) -> str:
        """
        Get formatted context for a query, suitable for LLM prompts.

        Args:
            query: Search query
            max_chars: Maximum characters to include in context

        Returns:
            Formatted context string
        """
        # Lazily initialize search if needed
        self._ensure_search_loaded()
        if not self.search:
            return "No relevant information found."

        results = self.search(query, limit=5)

        if not results:
            return "No relevant information found."

        context_parts = []
        current_length = 0

        for result in results:
            # Get GitHub URL for this document
            github_url = self._get_github_url(result["id"])

            # Truncate text if needed (allow more content per document)
            text = result["text"]

            # Add document info with both source path and GitHub link
            if github_url:
                # Extract filename for link text
                filename = result["id"].split("/")[-1]
                doc_info = f"Source: {result['id']}\nGitHub URL: <{github_url}|{filename}>\n"
            else:
                doc_info = f"Source: {result['id']}\n"

            content = f"{text}\n\n"

            # Check if adding this would exceed max_chars
            if current_length + len(doc_info) + len(content) > max_chars:
                break

            context_parts.append(doc_info + content)
            current_length += len(doc_info) + len(content)

        if not context_parts:
            return "No relevant information found."

        return "".join(context_parts).strip()

    def get_raw_results_for_ai(self, query: str, limit: int = 5) -> List[Dict[str, str]]:
        """
        Get raw RAG results with GitHub URLs for AI processing.

        Args:
            query: Search query
            limit: Maximum number of results to return

        Returns:
            List of dictionaries with 'id', 'text', 'score', and 'github_url' keys
        """
        # Lazily initialize search if needed
        self._ensure_search_loaded()
        if not self.search:
            return []

        results = self.search(query, limit)

        enhanced_results = []
        for result in results:
            github_url = self._get_github_url(result["id"])
            enhanced_results.append(
                {
                    "id": result["id"],
                    "text": result["text"],
                    "score": result["score"],
                    "github_url": github_url,
                    "model_score": result.get("model_score", 1.0),
                    "extension_weight": result.get("extension_weight", 1.0),
                    "adjusted_score": result.get("adjusted_score", result["score"]),
                }
            )

        return enhanced_results

    def get_detailed_context(self, query: str, max_chars: int = 6000) -> str:
        """
        Get detailed context with more content per document.

        Args:
            query: Search query
            max_chars: Maximum characters to include in context

        Returns:
            Formatted context string with more detailed content
        """
        # Lazily initialize search if needed
        self._ensure_search_loaded()
        if not self.search:
            return "No relevant information found."

        results = self.search(query, limit=2)  # Fewer results, more content each

        if not results:
            return "No relevant information found."

        context_parts = []
        current_length = 0

        for result in results:
            # Get GitHub URL for this document
            github_url = self._get_github_url(result["id"])

            # Allow much more content per document
            text = result["text"]

            # Add document info with both source path and GitHub link
            if github_url:
                # Extract filename for link text
                filename = result["id"].split("/")[-1]
                doc_info = f"Source: {result['id']}\nGitHub URL: <{github_url}|{filename}>\n"
            else:
                doc_info = f"Source: {result['id']}\n"

            content = f"{text}\n\n"

            # Check if adding this would exceed max_chars
            if current_length + len(doc_info) + len(content) > max_chars:
                break

            context_parts.append(doc_info + content)
            current_length += len(doc_info) + len(content)

        if not context_parts:
            return "No relevant information found."

        return "".join(context_parts).strip()

    def is_available(self) -> bool:
        """Check if the RAG service is available and ready."""
        # Ensure search is loaded and check its embeddings availability
        self._ensure_search_loaded()
        try:
            return bool(
                (self.general_embeddings is not None)
                or (self.search and getattr(self.search, "general_embeddings", None))
            )
        except Exception:
            return False

    async def search_docs(
        self,
        query: str,
        limit: int = 6,
        toolkit: str = None,
        doctype: str = None,
        threshold: float = 0.0,
    ) -> List[Dict]:
        """Search for documents with optional filtering."""
        # Ensure search is loaded before proceeding
        self._ensure_search_loaded()
        if not self.search:
            return []

        # Before searching, push runtime weights into search.model_weights (backwards compatibility)
        # Reload file-based weights so each search uses the latest on-disk configuration
        try:
            self.weights.reload()
        except Exception:
            # If reload fails, proceed with previously loaded values
            logger.debug("Failed to reload weights from disk; using cached values")

        # Inject file-based weights and any runtime overrides into the Search instance
        try:
            self.search.extension_weights = self.weights.extension_weights or {}
            # Start from the file-based model weights, then apply runtime overrides
            self.search.model_weights = dict(self.weights.model_weights or {})
        except Exception:
            # Defensive fallbacks
            self.search.extension_weights = {}
            self.search.model_weights = {}

        if self._weights:
            # Merge runtime weights, overriding file-based values
            self.search.model_weights.update(self._weights)

        # Get initial search results
        results = self.search.search(query, limit * 2)  # Get more to allow for filtering

        # Ensure results have expected scoring fields so downstream code can rely on them.
        for r in results:
            # If the search backend already provided model_score/extension_weight/
            # adjusted_score, preserve those values. Otherwise compute sensible
            # defaults based on current runtime weights so tests and callers can
            # rely on deterministic fields being present.
            try:
                # Determine the effective model_score: prefer explicit runtime
                # overrides found in the Search instance (self.search.model_weights).
                runtime_mw = getattr(self.search, "model_weights", {}) or {}
                if r.get("id") in runtime_mw:
                    r_model_score = float(runtime_mw.get(r.get("id"), 1.0))
                else:
                    # Fall back to provided value or default
                    r_model_score = float(r.get("model_score", 1.0))
                r["model_score"] = r_model_score
            except Exception:
                r["model_score"] = float(r.get("model_score", 1.0))

            try:
                # Determine effective extension weight: prefer search.extension_weights
                runtime_ext = getattr(self.search, "extension_weights", {}) or {}
                ext = Path(r.get("id", "")).suffix
                if ext in runtime_ext:
                    r_ext = float(runtime_ext.get(ext, 1.0))
                else:
                    r_ext = float(r.get("extension_weight", 1.0))
                r["extension_weight"] = r_ext
            except Exception:
                r["extension_weight"] = float(r.get("extension_weight", 1.0))

            try:
                # Recompute adjusted score from effective components unless the
                # search backend provided an explicit adjusted_score AND there
                # are no runtime overrides for this document or its extension.
                base = float(r.get("score", 0.0))
                has_runtime_model_override = r.get("id") in (getattr(self.search, "model_weights", {}) or {})
                ext_key = Path(r.get("id", "")).suffix
                has_runtime_ext_override = ext_key in (getattr(self.search, "extension_weights", {}) or {})

                if "adjusted_score" in r and not has_runtime_model_override and not has_runtime_ext_override:
                    # Preserve provided adjusted_score
                    r["adjusted_score"] = float(r["adjusted_score"])
                else:
                    r["adjusted_score"] = r.get("extension_weight", 1.0) * r.get("model_score", 1.0) * base
            except Exception:
                r["adjusted_score"] = float(r.get("adjusted_score", r.get("score", 0.0)))

        # Apply filters if specified
        if toolkit or doctype:
            filtered_results = []
            for result in results:
                doc_id = result["id"]
                meta = self.registry.get_meta(doc_id)

                # Check toolkit filter
                if toolkit and meta.toolkit != toolkit:
                    continue

                # Check doctype filter
                if doctype and meta.doctype != doctype:
                    continue

                filtered_results.append(result)
            results = filtered_results

        # Apply threshold filter
        if threshold > 0.0:
            results = [r for r in results if r["score"] >= threshold]

        # Return top results up to limit
        return results[:limit]

    async def retrieve(self, doc_id: str, start: int = None, end: int = None) -> Dict:
        """Retrieve a span of text from a document."""
        # Default full document if no range provided
        if start is None or end is None:
            text = self.store.read_lines(doc_id)
        else:
            text = self.store.read_lines(doc_id, start, end)
        meta = self.registry.get_meta(doc_id)
        return {
            "doc_id": doc_id,
            "text": text,
            "github_url": meta.github_url,
            "content_sha256": meta.content_sha256,
        }

    async def retrieve_batch(self, items: List[Dict]) -> List[Dict]:
        """Retrieve multiple text spans in batch."""
        results = []
        for item in items:
            doc_id = item["doc_id"]
            start = item.get("start")
            end = item.get("end")
            try:
                result = await self.retrieve(doc_id, start, end)
                results.append(result)
            except Exception as e:
                logger.error(f"Failed to retrieve {doc_id}: {e}")
                # Add placeholder with error info
                results.append(
                    {
                        "doc_id": doc_id,
                        "text": f"Error retrieving document: {str(e)}",
                        "github_url": "",
                        "content_sha256": "",
                        "error": str(e),
                    }
                )
        return results

    async def list_tree(self, prefix: str = "", depth: int = 2, max_entries: int = 500) -> List[Dict]:
        """List document IDs under a prefix as a tree structure."""
        # Lazily initialize search and prefer registry fallback if embeddings unavailable
        self._ensure_search_loaded()
        if not self.search or not getattr(self.search, "general_embeddings", None):
            # Fallback to registry-based approach if search/embeddings not available
            doc_ids = self.registry.list_ids(prefix)
        else:
            try:
                # Get all document IDs from the search index by doing a broad search
                # txtai doesn't have a direct "list all IDs" method, so we search for common terms
                all_results = []

                # Try several broad searches to get as many document IDs as possible
                search_terms = ["the", "and", "a", "import", "def", "class", "README", "docs"]
                seen_ids = set()

                for term in search_terms:
                    try:
                        results = self.search.general_embeddings.search(term, limit=2000)
                        for result in results:
                            doc_id = result.get("id", "")
                            if doc_id and doc_id not in seen_ids:
                                if not prefix or doc_id.startswith(prefix):
                                    all_results.append(doc_id)
                                    seen_ids.add(doc_id)
                    except Exception:
                        # Skip documents that can't be parsed
                        continue

                    # Stop if we have enough diverse results
                    if len(seen_ids) > 1000:
                        break

                # Filter by prefix
                if prefix:
                    doc_ids = [doc_id for doc_id in all_results if doc_id.startswith(prefix)]
                else:
                    doc_ids = all_results

            except Exception:
                # Fallback to registry-based approach if search fails
                doc_ids = self.registry.list_ids(prefix)

        # Convert flat list to tree structure
        tree_entries = []
        seen_paths = set()

        # First pass: collect ALL paths (not limited by max_entries) to properly detect directories
        all_paths = set()
        for doc_id in doc_ids:
            parts = doc_id.split("/")
            for i in range(1, min(len(parts), depth + 1) + 1):  # Go one level deeper to detect directories
                path = "/".join(parts[:i])
                all_paths.add(path)

        # Second pass: build tree entries (limited by max_entries for display)
        entries_added = 0
        for doc_id in doc_ids:
            if entries_added >= max_entries:
                break

            parts = doc_id.split("/")
            for i in range(1, min(len(parts), depth) + 1):
                path = "/".join(parts[:i])
                if path not in seen_paths:
                    seen_paths.add(path)

                    # Check if this path has any children (making it a directory)
                    is_directory = any(other_path.startswith(path + "/") for other_path in all_paths)

                    tree_entries.append(
                        {
                            "path": path,
                            "type": "directory" if is_directory else "file",
                            "doc_id": doc_id if i == len(parts) else None,
                        }
                    )
                    entries_added += 1

                    if entries_added >= max_entries:
                        break

        return tree_entries

    async def set_weight(
        self,
        doc_id: str,
        multiplier: float,
        namespace: str = "global",
        ttl_days: int = None,
    ) -> None:
        """Set model weight for a document (runtime only). Extra parameters ignored for backward compatibility."""
        if not hasattr(self, "_weights"):
            self._weights = {}
        try:
            m = float(multiplier)
        except Exception:
            m = 1.0
        # Clamp similar to search logic expectations
        m = max(0.1, min(m, 10.0))
        self._weights[doc_id] = m
        # Reflect in search if it is already loaded (so next call sees it)
        try:
            if self.search is not None:
                self.search.model_weights[doc_id] = m
        except Exception:
            # Ignore failures when search/embeddings aren't available
            pass
        logger.info(f"Runtime weight set for {doc_id}: {m}")

    async def version(self) -> Dict:
        """Return index and build version info, with robust error handling for build info and extra environment details."""
        import sys
        import platform
        from nancy_brain import __version__

        __build_sha__ = "unknown"
        __built_at__ = "unknown"
        try:
            from nancy_brain import _build_info

            __build_sha__ = getattr(_build_info, "__build_sha__", "unknown")
            __built_at__ = getattr(_build_info, "__built_at__", "unknown")
        except (ImportError, AttributeError, Exception):
            pass

        # Gather environment info
        python_version = platform.python_version()
        implementation = platform.python_implementation()
        environment = os.environ.get("CONDA_DEFAULT_ENV") or os.environ.get("VIRTUAL_ENV") or "unknown"

        # Try to get key dependency versions
        def get_version(pkg):
            try:
                return __import__(pkg).__version__
            except Exception:
                return "unknown"

        dependencies = {
            "fastapi": get_version("fastapi"),
            "pydantic": get_version("pydantic"),
            "txtai": get_version("txtai"),
            "faiss": get_version("faiss") if get_version("faiss") != "unknown" else get_version("faiss_cpu"),
            "torch": get_version("torch"),
            "transformers": get_version("transformers"),
        }

        return {
            "index_version": __version__,
            "build_sha": __build_sha__,
            "built_at": __built_at__,
            "python_version": python_version,
            "python_implementation": implementation,
            "environment": environment,
            "dependencies": dependencies,
        }

    async def health(self) -> Dict:
        """Return service health status."""
        try:
            # Basic health checks
            is_ready = self.registry is not None and self.store is not None and self.search is not None

            status = "ok" if is_ready else "degraded"

            return {
                "status": status,
                "registry_loaded": self.registry is not None,
                "store_loaded": self.store is not None,
                "search_loaded": self.search is not None,
            }
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return {"status": "error", "error": str(e)}
