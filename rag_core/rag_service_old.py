"""
RAG (Retrieval-Augmented Generation) service for the Slack bot.
Provides semantic search capabilities using txtai embeddings.
"""

import os
import logging
import yaml
from pathlib import Path
from typing import List, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

def get_file_type_category(doc_id: str) -> str:
    """
    Determine if file should be treated as code, mixed content, or documentation
    for dual embedding model weighting.
    
    Args:
        doc_id: Document identifier (path-like string)
        
    Returns:
        'code', 'mixed', or 'docs'
    """
    path = Path(doc_id)
    
    # Direct code files
    code_extensions = {'.py', '.js', '.ts', '.cpp', '.java', '.go', '.rs', '.c', '.h', '.css', '.scss', '.jsx', '.tsx'}
    if path.suffix in code_extensions:
        return 'code'
    
    # Converted notebooks (mixed code + documentation) 
    if '.nb' in path.suffixes or '.nb.txt' in str(path):
        return 'mixed'
    
    # Configuration files (often contain structured data that benefits from code understanding)
    config_extensions = {'.json', '.yaml', '.yml', '.toml', '.ini'}
    if path.suffix in config_extensions:
        return 'mixed'
    
    # Mixed content (markdown often contains code blocks)
    mixed_extensions = {'.md', '.rst'}
    if path.suffix in mixed_extensions:
        return 'mixed'
    
    # Pure documentation
    return 'docs'

class RAGService:
    """Service for retrieving relevant context from the knowledge base."""
    
    def __init__(self, 
                 embeddings_path: str = "knowledge_base/embeddings/index", 
                 config_path: str = "config/repositories.yml",
                 use_dual_embedding: Optional[bool] = None):
        """
        Initialize the RAG service.
        
        Args:
            embeddings_path: Path to the txtai embeddings index
            config_path: Path to the repositories configuration file
            use_dual_embedding: Whether to use dual embedding models (general + code).
                               If None, reads from USE_DUAL_EMBEDDING environment variable.
        """
        # Use Nancy's base directory from environment variable
        nancy_base = Path(os.environ.get("NANCY_BASE_DIR", "."))
        self.embeddings_path = nancy_base / embeddings_path
        self.config_path = nancy_base / config_path
        
        # Read dual embedding setting from environment if not explicitly set
        if use_dual_embedding is None:
            use_dual_embedding = os.environ.get("USE_DUAL_EMBEDDING", "true").lower() == "true"
        self.use_dual_embedding = use_dual_embedding
        
        # Get code embedding model from environment
        self.code_model = os.environ.get("CODE_EMBEDDING_MODEL", "microsoft/codebert-base")
        
        # Embeddings models
        self.general_embeddings = None  # General text model
        self.code_embeddings = None     # Code-specific model (if dual embedding enabled)
        
        self.repo_config = None
        self._load_config()
        self._load_embeddings()
        self.model_weights_path = Path(os.environ.get("NANCY_BASE_DIR", ".")) / "config" / "model_weights.yaml"
        self.model_weights = self._load_model_weights()
        self.extension_weights = self._load_extension_weights()
    
    def _load_config(self):
        """Load the repositories configuration."""
        try:
            with open(self.config_path, 'r') as f:
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
            
        parts = doc_id.split('/', 2)  # Split into category, repo_name, file_path
        if len(parts) < 3:
            return None
            
        category, repo_name, file_path = parts
        
        # Find the repository in config
        if category in self.repo_config:
            for repo in self.repo_config[category]:
                if repo['name'] == repo_name:
                    # Convert GitHub URL to blob URL
                    github_url = repo['url']
                    if github_url.endswith('.git'):
                        github_url = github_url[:-4]
                    return f"{github_url}/blob/master/{file_path}"
        
        return None
    
    def _load_embeddings(self):
        """Load the txtai embeddings index(es)."""
        try:
            from txtai.embeddings import Embeddings
            
            if not self.embeddings_path.exists():
                logger.warning(f"Embeddings index not found at {self.embeddings_path}")
                logger.info("Run the knowledge base build script first:")
                logger.info("python scripts/build_knowledge_base.py --category microlens_submit --dirty")
                return
            
            # Load general embeddings (current model)
            logger.info(f"Loading general embeddings from {self.embeddings_path}")
            self.general_embeddings = Embeddings()
            self.general_embeddings.load(str(self.embeddings_path))
            logger.info("General embeddings loaded successfully")
            
            # Load code embeddings if dual embedding is enabled
            if self.use_dual_embedding:
                code_embeddings_path = self.embeddings_path.parent / "code_index"
                if code_embeddings_path.exists():
                    logger.info(f"Loading code embeddings from {code_embeddings_path}")
                    logger.info(f"Using code model: {self.code_model}")
                    self.code_embeddings = Embeddings()
                    self.code_embeddings.load(str(code_embeddings_path))
                    logger.info("Code embeddings loaded successfully - dual embedding active")
                else:
                    logger.warning(f"Code embeddings not found at {code_embeddings_path}")
                    logger.info("Falling back to single embedding model")
                    self.use_dual_embedding = False
            else:
                logger.info("Dual embedding disabled - using single general model")
            
            # Backward compatibility: set self.embeddings to general model
            self.embeddings = self.general_embeddings
            
        except ImportError:
            logger.error("txtai not available. Please install with: pip install txtai")
        except Exception as e:
            logger.error(f"Failed to load embeddings: {e}")
    
    def _load_model_weights(self):
        if self.model_weights_path.exists():
            try:
                with open(self.model_weights_path, "r") as f:
                    return yaml.safe_load(f) or {}
            except Exception as e:
                logger.warning(f"Failed to load model weights: {e}")
        return {}
    
    def _load_extension_weights(self):
        weights_path = Path(__file__).parent.parent / "config/weights.yaml"
        if weights_path.exists():
            try:
                with open(weights_path, "r") as f:
                    return yaml.safe_load(f) or {}
            except Exception as e:
                logger.warning(f"Failed to load weights: {e}")
        return {}
    
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
        general_scores = {r['id']: r for r in general_results}
        code_scores = {r['id']: r for r in code_results}
        
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
            general_score = general_result['score'] if general_result else 0.0
            code_score = code_result['score'] if code_result else 0.0
            
            # Apply file-type-aware weighting
            file_type = get_file_type_category(doc_id)
            if file_type == 'code':
                # Code files: reduce code model influence to avoid too many low-level files
                dual_score = 0.6 * general_score + 0.4 * code_score
            elif file_type == 'mixed':
                # Mixed content: equal weighting
                dual_score = 0.5 * general_score + 0.5 * code_score
            else:
                # Documentation: favor general model
                dual_score = 0.8 * general_score + 0.2 * code_score
            
            # Create merged result
            merged_result = {
                'id': doc_id,
                'text': base_result['text'],
                'score': dual_score,  # Use dual score as primary score
                'general_score': general_score,
                'code_score': code_score,
                'file_type': file_type
            }
            merged_results.append(merged_result)
        
        # Sort by dual score and process with existing reweighting
        merged_results.sort(key=lambda r: r['score'], reverse=True)
        # Send all merged results - let _process_and_rank_results do the reweighting and limiting
        return self._process_and_rank_results(merged_results, limit, dual_scores=True)
    
    def _process_and_rank_results(self, results: List[Dict], limit: int, dual_scores: bool = False) -> List[Dict[str, str]]:
        """Apply extension weights, model weights, and final ranking."""
        formatted_results = []
        
        # Load weights config
        weights_cfg = self.extension_weights or {}
        ext_weights = weights_cfg.get('extensions', {})
        path_includes = weights_cfg.get('path_includes', {})
        
        for result in results:
            doc_id = result['id']
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
            base_score = result.get('score', 0.0)
            adjusted_score = weight * model_score * base_score
            
            # Build result dictionary
            result_dict = {
                'id': doc_id,
                'text': result['text'],
                'score': base_score,
                'extension_weight': weight,
                'model_score': model_score,
                'adjusted_score': adjusted_score
            }
            
            # Add dual embedding info if available
            if dual_scores:
                result_dict.update({
                    'general_score': result.get('general_score', 0.0),
                    'code_score': result.get('code_score', 0.0),
                    'file_type': result.get('file_type', 'unknown')
                })
            
            formatted_results.append(result_dict)
        
        # Sort by adjusted_score, descending
        formatted_results.sort(key=lambda r: r['adjusted_score'], reverse=True)
        
        # Log search results
        dual_info = " (dual embedding)" if dual_scores else ""
        logger.info(f"Found {len(formatted_results)} results{dual_info} (sorted by adjusted_score)")
        
        return formatted_results[:limit]
    
    def get_context_for_query(self, query: str, max_chars: int = 4000) -> str:
        """
        Get formatted context for a query, suitable for LLM prompts.
        
        Args:
            query: Search query
            max_chars: Maximum characters to include in context
            
        Returns:
            Formatted context string
        """
        results = self.search(query, limit=5)
        
        if not results:
            return "No relevant information found."
        
        context_parts = []
        current_length = 0
        
        for result in results:
            # Get GitHub URL for this document
            github_url = self._get_github_url(result['id'])
            
            # Truncate text if needed (allow more content per document)
            text = result['text']
            
            # Add document info with both source path and GitHub link
            if github_url:
                # Extract filename for link text
                filename = result['id'].split('/')[-1]
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
        results = self.search(query, limit)
        
        enhanced_results = []
        for result in results:
            github_url = self._get_github_url(result['id'])
            enhanced_results.append({
                'id': result['id'],
                'text': result['text'],
                'score': result['score'],
                'github_url': github_url,
                'model_score': result.get('model_score', 1.0),
                'extension_weight': result.get('extension_weight', 1.0),
                'adjusted_score': result.get('adjusted_score', result['score'])
            })
        
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
        results = self.search(query, limit=2)  # Fewer results, more content each
        
        if not results:
            return "No relevant information found."
        
        context_parts = []
        current_length = 0
        
        for result in results:
            # Get GitHub URL for this document
            github_url = self._get_github_url(result['id'])
            
            # Allow much more content per document
            text = result['text']
            
            # Add document info with both source path and GitHub link
            if github_url:
                # Extract filename for link text
                filename = result['id'].split('/')[-1]
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
        return self.general_embeddings is not None
    
    def get_embedding_status(self) -> Dict[str, bool]:
        """Get detailed status of embedding models."""
        return {
            'general_embeddings': self.general_embeddings is not None,
            'code_embeddings': self.code_embeddings is not None,
            'dual_embedding_active': self.use_dual_embedding and self.code_embeddings is not None
        }


# Global instance for the bot to use
rag_service = None

def get_rag_service() -> Optional[RAGService]:
    """Get the global RAG service instance."""
    global rag_service
    if rag_service is None:
        rag_service = RAGService()
    return rag_service 