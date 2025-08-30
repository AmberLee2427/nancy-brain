"""
Registry for document repositories.
"""

# imports
import logging
import yaml
from pathlib import Path
from typing import Optional, Dict, List
from .types import DocMeta, get_file_type_category

logger = logging.getLogger(__name__)


class ModelWeights:
    """Manage model weights for different file types."""

    def __init__(self, model_weights_path: Path):
        self.model_weights_path = model_weights_path
        self.model_weights = self._load_model_weights()
        self.extension_weights = self._load_extension_weights()

    def _load_model_weights(self):
        if self.model_weights_path.exists():
            try:
                with open(self.model_weights_path, "r") as f:
                    data = yaml.safe_load(f) or {}
                    # If the file looks like an extension-weight file (contains extensions/path_includes),
                    # treat it as not providing per-doc model weights.
                    if isinstance(data, dict) and ("extensions" in data or "path_includes" in data):
                        return {}
                    return data
            except Exception as e:
                logger.warning(f"Failed to load model weights: {e}")
        return {}

    def _load_extension_weights(self):
        # Prefer an index-specific weights file if present in the same directory as the
        # provided model_weights_path. Fall back to package-level config/weights.yaml.
        if hasattr(self, "model_weights_path") and self.model_weights_path:
            base = self.model_weights_path.parent
        else:
            base = Path(__file__).parent.parent

        index_weights = base / "index_weights.yaml"
        weights_path = base / "weights.yaml"
        target = index_weights if index_weights.exists() else weights_path
        if target.exists():
            try:
                with open(target, "r") as f:
                    return yaml.safe_load(f) or {}
            except Exception as e:
                logger.warning(f"Failed to load extension weights from {target}: {e}")
        return {}

    def reload(self):
        """Reload model weights and extension weights from disk.

        Call this before searches to ensure the latest file-based weights are used.
        """
        self.model_weights = self._load_model_weights()
        self.extension_weights = self._load_extension_weights()


class Registry:
    """Registry for document repositories."""

    def __init__(self, config_path: Path, use_dual_embedding: Optional[bool] = None):
        """Initialize registry and load repository configuration."""
        self.config_path = config_path
        self.use_dual_embedding = use_dual_embedding
        self.repo_config: Dict = {}
        self._load_config()
        # Load repository configuration on init
        self.repo_config: Dict = {}
        self._load_config()

    def _load_config(self):
        """Load the repositories configuration."""
        try:
            with open(self.config_path, "r") as f:
                self.repo_config = yaml.safe_load(f)
            logger.info(f"Loaded repository configuration from {self.config_path}")
        except Exception as e:
            logger.error(f"Failed to load repository configuration: {e}")
            self.repo_config = {}

    def _get_github_url(self, doc_id: str) -> Optional[str]:
        """
        Convert a document ID to a GitHub URL.

        Args:
            doc_id: Document ID in format "category/repo_name/path/to/file"

        Returns:
            GitHub URL or None if not found
        """
        if not self.repo_config:
            return None

        parts = doc_id.split("/", 2)  # Split into category, repo_name, file_path
        if len(parts) < 3:
            return None

        category, repo_name, file_path = parts

        # Find the repository in config
        if category in self.repo_config:
            for repo in self.repo_config[category]:
                if repo["name"] == repo_name:
                    # Convert GitHub URL to blob URL
                    github_url = repo["url"]
                    if github_url.endswith(".git"):
                        github_url = github_url[:-4]
                    return f"{github_url}/blob/master/{file_path}"

        return None

    def get_github_url(self, doc_id: str) -> Optional[str]:
        """Public method to retrieve GitHub URL for a document id."""
        return self._get_github_url(doc_id)

    def get_meta(self, doc_id: str) -> DocMeta:
        """Get metadata for a document id."""
        github_url = self.get_github_url(doc_id)
        default_branch = "master"
        toolkit = None
        doctype = get_file_type_category(doc_id)
        content_sha256 = ""
        line_index: list[int] = []
        return DocMeta(
            doc_id=doc_id,
            github_url=github_url or "",
            default_branch=default_branch,
            toolkit=toolkit,
            doctype=doctype,
            content_sha256=content_sha256,
            line_index=line_index,
        )

    def list_ids(self, prefix: str = "") -> List[str]:
        """List document IDs that start with the given prefix."""
        ids: List[str] = []
        # Iterate through categories and repos to build doc IDs
        for category, repos in self.repo_config.items():
            for repo in repos or []:
                name = repo.get("name")
                if not name:
                    continue
                doc_id = f"{category}/{name}"
                # If prefix is empty or doc_id matches prefix, include
                if not prefix or doc_id.startswith(prefix):
                    ids.append(doc_id)
        return ids
