"""
Search for relevant documents using embeddings.
"""

# imports
import logging
from pathlib import Path
from typing import List, Dict
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

            # Apply file-type-aware weighting
            file_type = get_file_type_category(doc_id)
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
                "text": base_result["text"],
                "score": dual_score,  # Use dual score as primary score
                "general_score": general_score,
                "code_score": code_score,
                "file_type": file_type,
            }
            merged_results.append(merged_result)

        # Sort by dual score and process with existing reweighting
        merged_results.sort(key=lambda r: r["score"], reverse=True)
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
            ext = Path(doc_id).suffix
            weight = ext_weights.get(ext, 1.0)
            doc_id_lower = doc_id.lower()

            # Apply path-based multipliers
            for keyword, mult in path_includes.items():
                if keyword.lower() in doc_id_lower:
                    weight *= mult

            # Apply model weight
            model_score = self.model_weights.get(doc_id, 1.0)
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
                "text": result["text"],
                "score": base_score,
                "extension_weight": weight,
                "model_score": model_score,
                "adjusted_score": adjusted_score,
            }

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

        return formatted_results[:limit]
