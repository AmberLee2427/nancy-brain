"""
Search for relevant documents using embeddings.
"""

# imports
import logging
from pathlib import Path
from typing import List, Dict
import re
import difflib
from nancy_brain.chunking import strip_chunk_suffix
from .types import get_file_type_category

logger = logging.getLogger(__name__)


class Search:
    """Search for relevant documents using embeddings."""

    def __init__(
        self,
        embeddings_path: Path,
        dual: bool = False,
        code_model: str = "microsoft/codebert-base",
        extension_weights: Dict = None,
        model_weights: Dict = None,
    ):
        """
        Initialize the Search with embeddings.
        """
        self.embeddings_path = embeddings_path
        self.use_dual_embedding = dual
        self.code_model = code_model
        self.extension_weights = extension_weights or {}
        self.model_weights = model_weights or {}
        self.general_embeddings = None
        self.code_embeddings = None
        # Load embedding indexes
        self._load_embeddings()

    def _load_embeddings(self):
        """Load txtai embeddings for general and code indexes."""
        try:
            from txtai.embeddings import Embeddings

            # Load general embeddings (index is in 'index' subdirectory)
            general_index = self.embeddings_path / "index"
            logger.info(f"Loading general embeddings from {general_index}")
            self.general_embeddings = Embeddings()
            self.general_embeddings.load(str(general_index))
            # Load code embeddings if dual embedding enabled
            if self.use_dual_embedding:
                code_index = self.embeddings_path / "code_index"
                if code_index.exists():
                    logger.info(f"Loading code embeddings from {code_index}")
                    self.code_embeddings = Embeddings()
                    self.code_embeddings.load(str(code_index))
                else:
                    logger.warning(f"Code embeddings not found at {code_index}")
                    self.code_embeddings = None
            else:
                self.code_embeddings = None
        except ImportError:
            logger.error("txtai not installed. Please install via `pip install txtai`")
            self.general_embeddings = None
            self.code_embeddings = None
        except Exception as e:
            logger.error(f"Failed to load embeddings: {e}")
            self.general_embeddings = None
            self.code_embeddings = None

    def search(self, query: str, limit: int = 5) -> List[Dict[str, str]]:
        """
        Search for relevant documents using dual embedding if available.

        Args:
            query: Search query
            limit: Maximum number of results to return

        Returns:
            List of dictionaries with 'id', 'text', and 'score' keys
        """
        if not self.general_embeddings:
            logger.warning("Embeddings not loaded, cannot perform search")
            return []

        try:
            # Get results from both models if dual embedding is active
            if self.use_dual_embedding and self.code_embeddings:
                return self._dual_embedding_search(query, limit)
            else:
                return self._single_embedding_search(query, limit)

        except Exception as e:
            logger.error(f"Search failed: {e}")
            return []

    def _single_embedding_search(self, query: str, limit: int) -> List[Dict[str, str]]:
        """Perform search with single embedding model (backward compatibility)."""
        results = self.general_embeddings.search(query, limit * 50)
        # Attach highlights computed from query
        for r in results:
            r.setdefault("highlights", [])
            # compute highlights here by reusing helper from _process_and_rank_results scope
            # simple approach: compute inline lightweight highlights
            try:
                tokens = [t for t in re.split(r"\s+", query.strip()) if len(t) > 0]
            except Exception:
                tokens = []
            r["highlights"] = []
            if tokens:
                lower_text = r.get("text", "").lower()
                for tok in tokens:
                    if not tok:
                        continue
                    start = 0
                    lower_tok = tok.lower()
                    while True:
                        idx = lower_text.find(lower_tok, start)
                        if idx == -1:
                            break
                        r["highlights"].append({"start": idx, "end": idx + len(tok), "type": "stem"})
                        start = idx + len(tok)
        return self._process_and_rank_results(results, limit, dual_scores=None)

    def _dual_embedding_search(self, query: str, limit: int) -> List[Dict[str, str]]:
        """Perform search with dual embedding models and merge results."""
        # Search both models with larger candidate pools for reweighting
        general_results = self.general_embeddings.search(query, limit * 50)
        code_results = self.code_embeddings.search(query, limit * 50)

        # Create dictionaries for quick lookup
        general_scores = {r["id"]: r for r in general_results}
        code_scores = {r["id"]: r for r in code_results}

        # Get all unique document IDs but limit to reasonable candidate pool
        all_doc_ids = set(general_scores.keys()) | set(code_scores.keys())

        # Merge results with dual scoring
        merged_results = []
        for doc_id in all_doc_ids:
            general_result = general_scores.get(doc_id)
            code_result = code_scores.get(doc_id)

            # Use the result with content (prefer general model if both have it)
            if general_result:
                base_result = general_result
            elif code_result:
                base_result = code_result
            else:
                continue

            # Calculate dual scores
            general_score = general_result["score"] if general_result else 0.0
            code_score = code_result["score"] if code_result else 0.0

            # Gather metadata and derive base document id for weighting
            metadata = {}
            try:
                if isinstance(base_result.get("data"), dict):
                    metadata = base_result.get("data", {}) or {}
                elif isinstance(base_result.get("metadata"), dict):
                    metadata = base_result.get("metadata", {}) or {}
            except Exception:
                metadata = {}
            base_doc_id = metadata.get("source_document") or strip_chunk_suffix(doc_id)

            # Apply file-type-aware weighting
            file_type = get_file_type_category(base_doc_id)
            if file_type == "code":
                # Code files: reduce code model influence to avoid too many low-level files
                dual_score = 0.6 * general_score + 0.4 * code_score
            elif file_type == "mixed":
                # Mixed content: equal weighting
                dual_score = 0.5 * general_score + 0.5 * code_score
            else:
                # Documentation: favor general model
                dual_score = 0.8 * general_score + 0.2 * code_score

            # Create merged result
            merged_result = {
                "id": doc_id,
                "text": base_result.get("text", ""),
                "score": dual_score,  # Use dual score as primary score
                "general_score": general_score,
                "code_score": code_score,
                "file_type": file_type,
                "data": metadata,
                "source_document": base_doc_id,
            }
            merged_results.append(merged_result)

        # Sort by dual score and attach simple highlights from query
        merged_results.sort(key=lambda r: r["score"], reverse=True)
        for r in merged_results:
            r.setdefault("highlights", [])
            try:
                tokens = [t for t in re.split(r"\s+", query.strip()) if len(t) > 0]
            except Exception:
                tokens = []
            if tokens:
                lower_text = r.get("text", "").lower()
                for tok in tokens:
                    if not tok:
                        continue
                    start = 0
                    lower_tok = tok.lower()
                    while True:
                        idx = lower_text.find(lower_tok, start)
                        if idx == -1:
                            break
                        r["highlights"].append({"start": idx, "end": idx + len(tok), "type": "stem"})
                        start = idx + len(tok)

        # Send all merged results - let _process_and_rank_results do the reweighting and limiting
        return self._process_and_rank_results(merged_results, limit, dual_scores=True)

    def _process_and_rank_results(
        self, results: List[Dict], limit: int, dual_scores: bool = False
    ) -> List[Dict[str, str]]:
        """Apply extension weights, model weights, and final ranking."""
        formatted_results = []

        # Load weights config
        weights_cfg = self.extension_weights or {}
        ext_weights = weights_cfg.get("extensions", {})
        path_includes = weights_cfg.get("path_includes", {})

        for result in results:
            doc_id = result["id"]
            metadata = {}
            if isinstance(result.get("data"), dict):
                metadata = result.get("data") or {}
            elif isinstance(result.get("metadata"), dict):
                metadata = result.get("metadata") or {}
            base_doc_id = metadata.get("source_document") or strip_chunk_suffix(doc_id)

            ext = Path(base_doc_id).suffix
            weight = ext_weights.get(ext, 1.0)
            doc_id_lower = base_doc_id.lower()

            # Apply path-based multipliers
            for keyword, mult in path_includes.items():
                if keyword.lower() in doc_id_lower:
                    weight *= mult

            # Apply model weight
            model_score = self.model_weights.get(base_doc_id, self.model_weights.get(doc_id, 1.0))
            try:
                model_score = float(model_score)
            except Exception:
                model_score = 1.0
            model_score = max(0.5, min(model_score, 2.0))

            # Calculate final adjusted score
            base_score = result.get("score", 0.0)
            adjusted_score = weight * model_score * base_score

            # Build result dictionary
            result_dict = {
                "id": doc_id,
                "source_document": base_doc_id,
                "text": result.get("text", ""),
                "score": base_score,
                "extension_weight": weight,
                "model_score": model_score,
                "adjusted_score": adjusted_score,
                "data": metadata,
            }
            if result.get("highlights") is not None:
                result_dict["highlights"] = result.get("highlights")

            # Add dual embedding info if available
            if dual_scores:
                result_dict.update(
                    {
                        "general_score": result.get("general_score", 0.0),
                        "code_score": result.get("code_score", 0.0),
                        "file_type": result.get("file_type", "unknown"),
                    }
                )

            formatted_results.append(result_dict)

        # Sort by adjusted_score, descending
        formatted_results.sort(key=lambda r: r["adjusted_score"], reverse=True)

        # Log search results
        dual_info = " (dual embedding)" if dual_scores else ""
        logger.info(f"Found {len(formatted_results)} results{dual_info} (sorted by adjusted_score)")

        # Compute lightweight highlights (offsets) for each result based on the query
        def compute_highlights(text: str, query: str) -> List[Dict]:
            highlights = []
            if not query or not text:
                return highlights

            tokens = [t for t in re.split(r"\s+", query.strip()) if len(t) > 0]
            if not tokens:
                return highlights

            lower_text = text.lower()

            # Exact (word-boundary) matches
            for tok in tokens:
                try:
                    pattern = r"\b" + re.escape(tok) + r"\b"
                    for m in re.finditer(pattern, text, flags=re.IGNORECASE):
                        highlights.append({"start": m.start(), "end": m.end(), "type": "exact"})
                except re.error:
                    continue

            # Stem-like matches: token as substring (not already covered)
            for tok in tokens:
                lower_tok = tok.lower()
                start = 0
                while True:
                    idx = lower_text.find(lower_tok, start)
                    if idx == -1:
                        break
                    end = idx + len(lower_tok)
                    # skip if overlapping an exact
                    if not any(
                        h["start"] <= idx < h["end"] or h["start"] < end <= h["end"]
                        for h in highlights
                        if h["type"] == "exact"
                    ):
                        highlights.append({"start": idx, "end": end, "type": "stem"})
                    start = end

            # Fuzzy matches: compare token to words in text using difflib
            words = list(re.finditer(r"\w+", text))
            for tok in tokens:
                for w in words:
                    word_text = w.group(0)
                    # skip if already covered
                    if any(h["start"] <= w.start() < h["end"] or h["start"] < w.end() <= h["end"] for h in highlights):
                        continue
                    try:
                        ratio = difflib.SequenceMatcher(None, tok.lower(), word_text.lower()).ratio()
                    except Exception:
                        ratio = 0.0
                    if ratio >= 0.7:
                        highlights.append({"start": w.start(), "end": w.end(), "type": "fuzzy"})

            # Merge and sort non-overlapping, preferring exact > stem > fuzzy
            type_priority = {"exact": 3, "stem": 2, "fuzzy": 1}
            # Sort by start, then by -priority
            highlights.sort(key=lambda h: (h["start"], -type_priority.get(h["type"], 0)))

            # Remove overlaps by keeping higher priority spans
            merged = []
            for h in highlights:
                if not merged:
                    merged.append(h)
                else:
                    last = merged[-1]
                    if h["start"] < last["end"]:
                        # overlap, keep the one with higher priority
                        if type_priority.get(h["type"], 0) > type_priority.get(last["type"], 0):
                            merged[-1] = h
                    else:
                        merged.append(h)

            return merged

        # If query not available in this scope, we can't compute highlights; skip.
        # The UI will prefer highlights if provided by the service layer. We add empty highlights here.
        for r in formatted_results:
            r.setdefault("highlights", [])

        return formatted_results[:limit]
