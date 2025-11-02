"""
This script processes all repositories in the config/repositories.yml file.
Orchestrates the full knowledge base build pipeline (cloning, direct txtai indexing).
"""

import os

import warnings
import sys

# Allow duplicate OpenMP runtime loading when not explicitly configured. This mirrors
# the CLI behavior so builds don't abort due to multiple libomp copies.
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

import yaml
import subprocess
from pathlib import Path
import logging
import argparse
import requests
import json
import time
import threading
from typing import Optional, Set, Dict

try:
    from dotenv import load_dotenv
except Exception:
    load_dotenv = None

from chunky import ChunkPipeline, ChunkerConfig, Document
from nancy_brain.chunking import strip_chunk_suffix
from nancy_brain.summarization import SummaryGenerator

# Optional imports
try:
    from nb4llm import convert_ipynb_to_txt
except ImportError:
    convert_ipynb_to_txt = None

# Load .env overrides early so subsequent imports see them
if load_dotenv is not None:
    try:
        script_root = Path(__file__).resolve().parent.parent
        env_path = script_root / "config" / ".env"
        if env_path.exists():
            load_dotenv(env_path)
    except Exception:
        pass

# Ensure OpenMP duplicate setting persists after dotenv loads
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

# Add import for direct Tika PDF processing
# Suppress a noisy deprecation warning coming from tika's use of pkg_resources
try:
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            category=UserWarning,
            message=r"pkg_resources is deprecated as an API.*",
        )
        import tika
        from tika import parser as tika_parser

    TIKA_AVAILABLE = True
except ImportError:
    TIKA_AVAILABLE = False
except Exception:
    # If any other import-time error occurs, disable Tika but continue with fallback methods.
    TIKA_AVAILABLE = False

# Global flag (fix for previous scoping issue)
tika_ready = False

# PDF exclusion & thresholds
MIN_PDF_BYTES = int(os.environ.get("MIN_PDF_BYTES", "5000"))  # skip tiny/image-y PDFs
MIN_PDF_TEXT_CHARS = int(os.environ.get("MIN_PDF_TEXT_CHARS", "500"))  # require meaningful text
DEFAULT_EXCLUDE_PDF_SUBSTRINGS = [
    "logo/",
    "PointSpreadFunctions/",
    "PSF_",
    "PSFs_",
    "PSF-",
    "PSF.",
    "/graphics/",
    "workflow-",
    "Glossary.pdf",
    "column-mapping.pdf",
]
ENV_EXCLUDES = [e.strip() for e in os.environ.get("PDF_EXCLUDE_SUBSTRINGS", "").split(",") if e.strip()]
EXCLUDE_PDF_SUBSTRINGS = DEFAULT_EXCLUDE_PDF_SUBSTRINGS + ENV_EXCLUDES
README_CANDIDATES = ["README.md", "README.rst", "README.txt"]
DEFAULT_SUMMARIES_ENABLED = os.environ.get("ENABLE_DOC_SUMMARIES", "false").lower() == "true"
SKIP_PDFS = os.environ.get("SKIP_PDF_PROCESSING", "").strip().lower() == "true"
TEXT_EXTENSIONS = {".py", ".md", ".txt", ".rst", ".tex", ".yaml", ".yml", ".json"}
SKIP_DIR_NAMES = {
    ".git",
    ".github",
    "__pycache__",
    "node_modules",
    ".pytest_cache",
    ".mypy_cache",
    ".idea",
    ".venv",
    "env",
    "venv",
}


def is_excluded_pdf(path: str) -> bool:
    p = str(path)
    return any(token in p for token in EXCLUDE_PDF_SUBSTRINGS)


def load_repo_readme(repo_dir: Path) -> Optional[dict]:
    for candidate in README_CANDIDATES:
        readme_path = repo_dir / candidate
        if not readme_path.exists():
            continue
        try:
            text = readme_path.read_text(encoding="utf-8")
        except Exception:
            continue
        if text.strip():
            try:
                relative = str(readme_path.relative_to(repo_dir))
            except Exception:
                relative = str(readme_path.name)
            return {"content": text, "path": relative}
    return None


def collect_repo_files(repo_dir: Path) -> tuple[list[Path], list[Path]]:
    text_files: list[Path] = []
    pdf_files: list[Path] = []
    for root, dirs, files in os.walk(repo_dir):
        dirs[:] = [d for d in dirs if d not in SKIP_DIR_NAMES]
        for filename in files:
            path = Path(root) / filename
            suffix = path.suffix.lower()
            if suffix in TEXT_EXTENSIONS or filename.endswith(".nb.txt"):
                text_files.append(path)
            elif suffix == ".pdf" and not SKIP_PDFS:
                pdf_files.append(path)
    return text_files, pdf_files


def emit_progress(percent: int, stage: str = "", detail: str = ""):
    """Emit a JSON progress marker line to stdout for UIs to parse.

    Lines are prefixed with PROGRESS_JSON: to make them easy to detect in logs.
    """
    try:
        payload = {"percent": int(percent), "stage": stage, "detail": detail}
        print("PROGRESS_JSON: " + json.dumps(payload), flush=True)
    except Exception:
        # Never fail the build due to progress emission
        pass


# PDF download headers
PDF_REQUEST_HEADERS = {
    "User-Agent": "nancy-brain-kb-builder/0.1 (+https://example.local)",
    "Accept": "application/pdf,application/octet-stream;q=0.9,*/*;q=0.8",
}

# --- Fallback PDF extraction methods (original content) ---


def extract_text_fallback(pdf_path):
    import logging

    logger = logging.getLogger(__name__)
    try:
        import PyPDF2

        with open(pdf_path, "rb") as file:
            reader = PyPDF2.PdfReader(file)
            text = ""
            for page in reader.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
            if len(text.strip()) > 100:
                return text.strip()
    except Exception:
        pass
    try:
        import pdfplumber

        text = ""
        with pdfplumber.open(pdf_path) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
        if len(text.strip()) > 100:
            return text.strip()
    except Exception:
        pass
    try:
        import fitz

        doc = fitz.open(str(pdf_path))
        text = ""
        for page in doc:
            text += page.get_text() + "\n"
        doc.close()
        if len(text.strip()) > 100:
            return text.strip()
    except Exception:
        pass
    return None


# --- Modified process_pdf_with_fallback with global tika_ready ---


def process_pdf_with_fallback(pdf_path, repo_info=None, article_info=None):
    logger = logging.getLogger(__name__)
    global tika_ready
    if TIKA_AVAILABLE and not tika_ready and not SKIP_PDFS:
        try:
            os.environ.setdefault("TIKA_CLIENT_TIMEOUT", "60")
            os.environ.setdefault("TIKA_SERVER_TIMEOUT", "60")
            os.environ.setdefault("TIKA_STARTUP_TIMEOUT", "120")
            tika.initVM()
            tika_ready = True
            logger.info("✅ Tika VM initialized (lazy) for PDF processing")
        except Exception as e:
            logger.warning(f"Failed lazy Tika init: {e}")
    if TIKA_AVAILABLE and tika_ready and not SKIP_PDFS:
        try:
            parsed = tika_parser.from_file(str(pdf_path))
            content = parsed.get("content", "") if parsed else ""
            if content and len(content.strip()) > 100:
                return content.strip(), True
        except Exception as e:
            logger.warning(f"Tika processing failed for {pdf_path}: {e}")
    logger.info(f"Using fallback PDF extraction for {pdf_path}")
    content = extract_text_fallback(pdf_path)
    if content:
        # Enforce minimum extracted chars
        if len(content) < MIN_PDF_TEXT_CHARS:
            logger.debug(f"Discarding PDF {pdf_path} (extracted chars {len(content)} < {MIN_PDF_TEXT_CHARS})")
            return None, False
        return content, True
    else:
        logger.warning(f"All PDF extraction methods failed for {pdf_path}")
        return None, False


# --- Utility function (unchanged from original) ---


def get_file_type_category(doc_id: str) -> str:
    base_id = strip_chunk_suffix(doc_id)
    path = Path(base_id)
    code_extensions = {
        ".py",
        ".js",
        ".ts",
        ".cpp",
        ".java",
        ".go",
        ".rs",
        ".c",
        ".h",
        ".css",
        ".scss",
        ".jsx",
        ".tsx",
    }
    if path.suffix in code_extensions:
        return "code"
    if ".nb" in path.suffixes or ".nb.txt" in str(path):
        return "mixed"
    config_extensions = {".json", ".yaml", ".yml", ".toml", ".ini"}
    if path.suffix in config_extensions:
        return "mixed"
    mixed_extensions = {".md", ".rst"}
    if path.suffix in mixed_extensions:
        return "mixed"
    return "docs"


# --- Updated download function with headers ---


def download_pdf_articles(
    config_path: str,
    base_path: str = "knowledge_base/raw",
    dry_run: bool = False,
    category: str = None,
    force_update: bool = False,
) -> dict:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
    logger = logging.getLogger(__name__)
    with open(config_path, "r") as f:
        config = yaml.safe_load(f)
    session = requests.Session()
    session.headers.update(PDF_REQUEST_HEADERS)
    session.max_redirects = 15
    categories = [category] if category else list(config.keys())
    failures = {
        "failed_downloads": [],
        "skipped_existing": [],
        "successful_downloads": [],
    }
    for cat in categories:
        articles = config.get(cat)
        if not isinstance(articles, list):
            continue
        for article in articles:
            article_name = article["name"]
            article_url = article["url"]
            dest_dir = Path(base_path) / cat
            dest_file = dest_dir / f"{article_name}.pdf"
            if dest_file.exists() and not force_update:
                logger.info(f"Article {cat}/{article_name}.pdf already exists, skipping.")
                failures["skipped_existing"].append(f"{cat}/{article_name}")
                continue
            logger.info(f"Downloading {article_name} from {article_url} to {dest_file}...")
            if dry_run:
                logger.info(f"[DRY RUN] Would download {article_url} to {dest_file}")
                continue
            dest_dir.mkdir(parents=True, exist_ok=True)
            try:
                resp = session.get(article_url, timeout=45, allow_redirects=True)
                resp.raise_for_status()
                ct = resp.headers.get("Content-Type", "")
                if "text/html" in ct.lower():
                    raise RuntimeError(f"Expected PDF got HTML (content-type={ct})")
                if len(resp.content) < MIN_PDF_BYTES:
                    raise RuntimeError(f"PDF too small ({len(resp.content)} bytes < {MIN_PDF_BYTES})")
                with open(dest_file, "wb") as f:
                    f.write(resp.content)
                logger.info(f"Successfully downloaded {article_name}")
                failures["successful_downloads"].append(f"{cat}/{article_name}")
            except requests.TooManyRedirects as e:
                logger.error(f"Failed to download {article_name}: Redirect loop ({e})")
                failures["failed_downloads"].append(f"{cat}/{article_name}: Redirect loop")
            except Exception as e:
                if dest_file.exists():
                    try:
                        dest_file.unlink()
                    except Exception:
                        pass
                logger.error(f"Failed to download {article_name}: {e}")
                failures["failed_downloads"].append(f"{cat}/{article_name}: {str(e)}")
    return failures


# --- Clone repositories (original) ---


def clone_repositories(
    config_path: str,
    base_path: str = "knowledge_base/raw",
    dry_run: bool = False,
    category: str = None,
    force_update: bool = False,
) -> dict:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
    logger = logging.getLogger(__name__)
    with open(config_path, "r") as f:
        config = yaml.safe_load(f)
    categories = [category] if category else list(config.keys())
    failures = {
        "failed_clones": [],
        "failed_updates": [],
        "skipped_existing": [],
        "successful_clones": [],
        "successful_updates": [],
    }
    for cat in categories:
        repos = config.get(cat)
        if not isinstance(repos, list):
            continue
        for repo in repos:
            repo_name = repo["name"]
            repo_url = repo["url"]
            dest_dir = Path(base_path) / cat / repo_name
            if dest_dir.exists():
                if force_update:
                    logger.info(f"Repository {cat}/{repo_name} exists. Updating...")
                    if dry_run:
                        logger.info(f"[DRY RUN] Would update {cat}/{repo_name}")
                        continue
                    try:
                        subprocess.run(
                            ["git", "fetch", "--all"],
                            cwd=str(dest_dir),
                            check=True,
                            capture_output=True,
                            text=True,
                        )
                        result = subprocess.run(
                            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                            cwd=str(dest_dir),
                            capture_output=True,
                            text=True,
                        )
                        current_branch = result.stdout.strip()
                        subprocess.run(
                            ["git", "pull", "origin", current_branch],
                            cwd=str(dest_dir),
                            check=True,
                            capture_output=True,
                            text=True,
                        )
                        failures["successful_updates"].append(f"{cat}/{repo_name}")
                    except subprocess.CalledProcessError as e:
                        failures["failed_updates"].append(f"{cat}/{repo_name}: {e.stderr}")
                else:
                    logger.info(f"Repository {cat}/{repo_name} already exists, skipping.")
                    failures["skipped_existing"].append(f"{cat}/{repo_name}")
            else:
                logger.info(f"Cloning {repo_name} from {repo_url} into {dest_dir}...")
                if dry_run:
                    logger.info(f"[DRY RUN] Would clone {repo_url} into {dest_dir}")
                    continue
                dest_dir.parent.mkdir(parents=True, exist_ok=True)
                try:
                    subprocess.run(
                        ["git", "clone", repo_url, str(dest_dir)],
                        check=True,
                        capture_output=True,
                        text=True,
                    )
                    failures["successful_clones"].append(f"{cat}/{repo_name}")
                except subprocess.CalledProcessError as e:
                    failures["failed_clones"].append(f"{cat}/{repo_name}: {e.stderr}")
    return failures


# --- Build index (original with early Tika fix) ---


def build_txtai_index(
    config_path: str,
    articles_config_path: str = None,
    base_path: str = "knowledge_base/raw",
    embeddings_path: str = "knowledge_base/embeddings",
    dry_run: bool = False,
    category: str = None,
    summary_generator: Optional[SummaryGenerator] = None,
) -> dict:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
    logger = logging.getLogger(__name__)
    try:
        from txtai.embeddings import Embeddings
    except ImportError:
        logger.error("txtai not available. Please install with: pip install txtai")
        return {
            "failed_text_files": [],
            "failed_pdf_files": [],
            "failed_notebook_conversions": [],
            "successful_text_files": 0,
            "successful_pdf_files": 0,
            "successful_notebook_conversions": 0,
            "skipped_repositories": [],
            "skipped_articles": [],
        }
    use_dual_embedding = os.environ.get("USE_DUAL_EMBEDDING", "true").lower() == "true"
    code_model = os.environ.get("CODE_EMBEDDING_MODEL", "microsoft/codebert-base")
    logger.info(f"Dual embedding enabled: {use_dual_embedding}")
    if use_dual_embedding:
        logger.info(f"Code model: {code_model}")
    if SKIP_PDFS:
        logger.info("SKIP_PDF_PROCESSING enabled; PDF documents will be ignored during build.")
    global tika_ready
    pdf_fallback_available = False
    try:
        import PyPDF2  # noqa: F401

        pdf_fallback_available = True
        logger.info("✅ PyPDF2 available as fallback")
    except Exception:
        try:
            import pdfplumber  # noqa: F401

            pdf_fallback_available = True
            logger.info("✅ pdfplumber available as fallback")
        except Exception:
            pass
    if TIKA_AVAILABLE and not tika_ready and not SKIP_PDFS:
        try:
            os.environ.setdefault("TIKA_CLIENT_TIMEOUT", "60")
            os.environ.setdefault("TIKA_SERVER_TIMEOUT", "60")
            os.environ.setdefault("TIKA_STARTUP_TIMEOUT", "120")
            tika.initVM()
            tika_ready = True
            logger.info("✅ Tika VM initialized for PDF processing")
        except Exception as e:
            logger.warning(f"Failed to initialize Tika VM: {e}. Will use fallback methods if available.")
    try:
        with open(config_path, "r") as f:
            config = yaml.safe_load(f)
    except Exception as e:
        logger.error(f"Failed to read repository config: {config_path} ({e})")
        return {
            "failed_text_files": [],
            "failed_pdf_files": [],
            "failed_notebook_conversions": [],
            "successful_text_files": 0,
            "successful_pdf_files": 0,
            "successful_notebook_conversions": 0,
            "skipped_repositories": [],
            "skipped_articles": [],
            "validation_errors": [f"Failed to read config: {config_path}: {e}"],
        }

    # Validate repository config early to give clear feedback
    try:
        from nancy_brain.config_validation import validate_repositories_config, validate_articles_config

        ok, errors = validate_repositories_config(config or {})
        if not ok:
            logger.error("repositories.yml validation failed")
            return {
                "failed_text_files": [],
                "failed_pdf_files": [],
                "failed_notebook_conversions": [],
                "successful_text_files": 0,
                "successful_pdf_files": 0,
                "successful_notebook_conversions": 0,
                "skipped_repositories": [],
                "skipped_articles": [],
                "validation_errors": errors,
            }
    except Exception:
        # If validation helpers are unavailable for any reason, continue without failing
        pass

    articles_config = {}
    if articles_config_path and os.path.exists(articles_config_path):
        with open(articles_config_path, "r") as f:
            articles_config = yaml.safe_load(f)
        logger.info(f"Loaded articles configuration from {articles_config_path}")
        # Validate articles config if validator available
        try:
            ok2, errors2 = validate_articles_config(articles_config or {})
            if not ok2:
                logger.error("articles.yml validation failed")
                return {
                    "failed_text_files": [],
                    "failed_pdf_files": [],
                    "failed_notebook_conversions": [],
                    "successful_text_files": 0,
                    "successful_pdf_files": 0,
                    "successful_notebook_conversions": 0,
                    "skipped_repositories": [],
                    "skipped_articles": [],
                    "validation_errors": errors2,
                }
        except Exception:
            pass
    embeddings_dir = Path(embeddings_path)
    embeddings_dir.mkdir(parents=True, exist_ok=True)
    text_model = os.environ.get("NB_TEXT_EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
    logger.info(f"Loading general embedding model: {text_model}")
    model_start = time.time()
    try:
        general_embeddings = Embeddings(
            {
                "path": text_model,
                "content": True,
                "backend": "faiss",
            }
        )
    except Exception as exc:
        logger.error(f"Failed to load general embedding model '{text_model}': {exc}")
        logger.error(
            "If this is the first run, ensure the model is reachable or set NB_TEXT_EMBEDDING_MODEL"
            " to a smaller/local SentenceTransformer."
        )
        raise
    logger.info(f"General embedding model ready in {time.time() - model_start:.2f}s")
    code_embeddings = None
    if use_dual_embedding:
        code_model_override = os.environ.get("NB_CODE_EMBEDDING_MODEL", code_model)
        logger.info(f"Loading code embedding model: {code_model_override}")
        code_start = time.time()
        try:
            code_embeddings = Embeddings({"path": code_model_override, "content": True, "backend": "faiss"})
        except Exception as exc:
            logger.error(f"Failed to load code embedding model '{code_model_override}': {exc}")
            logger.error(
                "Disable dual embeddings with USE_DUAL_EMBEDDING=false or set NB_CODE_EMBEDDING_MODEL"
                " to a lighter model."
            )
            raise
        logger.info(f"Code embedding model ready in {time.time() - code_start:.2f}s")
    try:
        with open("config/index_weights.yaml", "r") as f:
            ext_weights = yaml.safe_load(f)
    except Exception:
        ext_weights = {}
    categories = [category] if category else list(config.keys())
    documents = []
    pipeline = ChunkPipeline()
    chunk_config = ChunkerConfig(
        max_chars=int(os.environ.get("CHUNKY_MAX_CHARS", "2000")),
        lines_per_chunk=int(os.environ.get("CHUNKY_LINES_PER_CHUNK", "80")),
        line_overlap=int(os.environ.get("CHUNKY_LINE_OVERLAP", "10")),
    )
    pdf_status = {}  # doc_id -> {status, size, chars, method}
    failures = {
        "failed_text_files": [],
        "failed_pdf_files": [],
        "failed_notebook_conversions": [],
        "successful_text_files": 0,
        "successful_pdf_files": 0,
        "successful_notebook_conversions": 0,
        "skipped_repositories": [],
        "skipped_articles": [],
        "skipped_low_value": [],
        "fatal_errors": [],
    }
    text_candidate_count = 0
    pdf_candidate_count = 0
    summary_documents = []
    summary_enabled = False
    if summary_generator is not None:
        summary_enabled = bool(getattr(summary_generator, "enabled", True))
    summary_stats = {
        "configured": summary_generator is not None,
        "enabled": summary_enabled,
        "requests": 0,
        "responses": 0,
        "cached_hits": 0,
        "failures": 0,
        "documents_added": 0,
    }
    auto_model_weights: Dict[str, float] = {}
    summarized_docs: Set[str] = set()
    repo_readme_cache: Dict[Path, Optional[dict]] = {}
    for cat in categories:
        repos = config.get(cat)
        if not isinstance(repos, list):
            continue
        for repo in repos:
            repo_name = repo["name"]
            repo_dir = Path(base_path) / cat / repo_name
            if not repo_dir.exists():
                failures["skipped_repositories"].append(f"{cat}/{repo_name}")
                continue
            repo_readme_content = None
            repo_readme_path = None
            if summary_generator is not None:
                if repo_dir not in repo_readme_cache:
                    repo_readme_cache[repo_dir] = load_repo_readme(repo_dir)
                repo_readme_info = repo_readme_cache.get(repo_dir) or {}
                repo_readme_content = repo_readme_info.get("content")
                repo_readme_path = repo_readme_info.get("path")
            if convert_ipynb_to_txt is not None:
                for ipynb_file in repo_dir.rglob("*.ipynb"):
                    nb_txt_file = ipynb_file.with_suffix(".nb.txt")
                    if not nb_txt_file.exists() or ipynb_file.stat().st_mtime > nb_txt_file.stat().st_mtime:
                        try:
                            convert_ipynb_to_txt(str(ipynb_file), str(nb_txt_file))
                            failures["successful_notebook_conversions"] += 1
                        except Exception as e:
                            failures["failed_notebook_conversions"].append(f"{ipynb_file}: {str(e)}")
            text_files, pdf_files = collect_repo_files(repo_dir)
            if SKIP_PDFS:
                pdf_files = []
            else:
                filtered_pdf_files = []
                for pf in pdf_files:
                    try:
                        if is_excluded_pdf(pf):
                            pdf_status[str(pf)] = {
                                "status": "excluded",
                                "reason": "pattern",
                                "size": pf.stat().st_size if pf.exists() else 0,
                            }
                            continue
                        size = pf.stat().st_size
                        if size < MIN_PDF_BYTES:
                            pdf_status[str(pf)] = {
                                "status": "skipped",
                                "reason": f"small({size})",
                                "size": size,
                            }
                            continue
                        filtered_pdf_files.append(pf)
                    except Exception:
                        continue
                pdf_files = filtered_pdf_files
            text_files = [f for f in text_files if "docs/build" not in str(f) and not str(f).endswith(".rst.txt")]
            if (
                os.environ.get("NB_SCAN_LOG", "false").lower() == "true"
                or os.environ.get("NB_PER_FILE_LOG", "false").lower() == "true"
            ):
                logger.info(
                    f"Repo {repo_name}: {len(text_files)} candidate text files, {len(pdf_files)} candidate PDFs"
                )
            # Use text extraction helpers for .rst and .tex files when available
            try:
                from scripts.text_extract import extract_text_from_rst, extract_text_from_tex
            except Exception:
                extract_text_from_rst = None
                extract_text_from_tex = None

            for file_path in text_files:
                try:
                    text_candidate_count += 1
                    logger.info(f"Reading file {file_path.relative_to(repo_dir)}")
                    with open(file_path, "r", encoding="utf-8") as f:
                        content = f.read()
                    if not content.strip():
                        continue
                    suffix = file_path.suffix.lower()
                    if suffix == ".rst" and extract_text_from_rst:
                        try:
                            content = extract_text_from_rst(content)
                        except Exception:
                            pass
                    if suffix == ".tex" and extract_text_from_tex:
                        try:
                            content = extract_text_from_tex(content)
                        except Exception:
                            pass
                    if not content or not content.strip():
                        continue
                    relative_path = file_path.relative_to(repo_dir)
                    doc_id = f"{cat}/{repo_name}/{relative_path}"
                    logger.info(f"Chunking file {doc_id}")
                    if summary_generator is not None and summary_stats["enabled"] and doc_id not in summarized_docs:
                        summary_stats["requests"] += 1
                        summary_payload = None
                        failed_due_to_exception = False
                        try:
                            summary_payload = summary_generator.summarize(
                                doc_id=doc_id,
                                content=content,
                                repo_name=repo_name,
                                repo_readme=repo_readme_content,
                                repo_readme_path=repo_readme_path,
                                metadata={"category": cat, "source": "repository_file"},
                            )
                        except Exception as exc:
                            failed_due_to_exception = True
                            summary_stats["failures"] += 1
                            logger.warning("Summary generation failed for %s: %s", doc_id, exc)
                        if summary_payload is not None:
                            summary_stats["responses"] += 1
                            if summary_payload.cached:
                                summary_stats["cached_hits"] += 1
                            summary_meta = {
                                "source_document": doc_id,
                                "category": cat,
                                "repository": repo_name,
                                "doc_type": "summary",
                                "model": summary_payload.model,
                                "cached": summary_payload.cached,
                            }
                            if summary_payload.repo_readme_path:
                                summary_meta["repo_readme_path"] = summary_payload.repo_readme_path
                            summary_documents.append(
                                (
                                    f"summaries/{doc_id}",
                                    summary_payload.summary,
                                    json.dumps(summary_meta, ensure_ascii=False),
                                )
                            )
                            auto_model_weights[doc_id] = summary_payload.weight
                            summarized_docs.add(doc_id)
                        elif not failed_due_to_exception:
                            summary_stats["failures"] += 1
                    document = Document(path=file_path, content=content, metadata={"doc_id": doc_id})
                    chunks = pipeline.chunk_documents([document], config=chunk_config)
                    if not chunks:
                        logger.debug(f"Skipping low-value document: {doc_id}")
                        failures["skipped_low_value"].append(doc_id)
                        continue
                    for chunk in chunks:
                        meta = dict(chunk.metadata)
                        meta.setdefault("extension", suffix)
                        meta.setdefault("relative_path", str(relative_path))
                        meta.setdefault("repository", repo_name)
                        documents.append(
                            (
                                chunk.chunk_id,
                                chunk.text,
                                json.dumps(meta, ensure_ascii=False),
                            )
                        )
                    failures["successful_text_files"] += 1
                except Exception as e:
                    failures["failed_text_files"].append(f"{file_path}: {str(e)}")
            for pdf_path in pdf_files:
                try:
                    pdf_candidate_count += 1
                    content, success = process_pdf_with_fallback(pdf_path, repo_info=repo)
                    size = pdf_path.stat().st_size if pdf_path.exists() else 0
                    if success and content:
                        relative_path = pdf_path.relative_to(repo_dir)
                        doc_id = f"{cat}/{repo_name}/{relative_path}"
                        metadata = (
                            f"Source: Repository PDF from {repo['url']}\n"
                            f"Path: {relative_path}\nType: Repository Document\n\n"
                        )
                        full_content = metadata + content
                        if summary_generator is not None and summary_stats["enabled"] and doc_id not in summarized_docs:
                            summary_stats["requests"] += 1
                            summary_payload = None
                            failed_due_to_exception = False
                            try:
                                summary_payload = summary_generator.summarize(
                                    doc_id=doc_id,
                                    content=full_content,
                                    repo_name=repo_name,
                                    repo_readme=repo_readme_content,
                                    repo_readme_path=repo_readme_path,
                                    metadata={"category": cat, "source": "repository_pdf"},
                                )
                            except Exception as exc:
                                failed_due_to_exception = True
                                summary_stats["failures"] += 1
                                logger.warning("Summary generation failed for %s: %s", doc_id, exc)
                            if summary_payload is not None:
                                summary_stats["responses"] += 1
                                if summary_payload.cached:
                                    summary_stats["cached_hits"] += 1
                                summary_meta = {
                                    "source_document": doc_id,
                                    "category": cat,
                                    "repository": repo_name,
                                    "doc_type": "summary",
                                    "model": summary_payload.model,
                                    "cached": summary_payload.cached,
                                }
                                if summary_payload.repo_readme_path:
                                    summary_meta["repo_readme_path"] = summary_payload.repo_readme_path
                                summary_documents.append(
                                    (
                                        f"summaries/{doc_id}",
                                        summary_payload.summary,
                                        json.dumps(summary_meta, ensure_ascii=False),
                                    )
                                )
                                auto_model_weights[doc_id] = summary_payload.weight
                                summarized_docs.add(doc_id)
                            elif not failed_due_to_exception:
                                summary_stats["failures"] += 1
                        document = Document(path=pdf_path, content=full_content, metadata={"doc_id": doc_id})
                        chunks = pipeline.chunk_documents([document], config=chunk_config)
                        if not chunks:
                            logger.debug(f"Skipping low-value PDF: {doc_id}")
                            failures["skipped_low_value"].append(doc_id)
                            continue
                        for chunk in chunks:
                            meta = dict(chunk.metadata)
                            meta.setdefault("relative_path", str(relative_path))
                            meta.setdefault("repository", repo_name)
                            meta.setdefault("pdf_size_bytes", size)
                            meta.setdefault("source_url", repo.get("url"))
                            documents.append(
                                (
                                    chunk.chunk_id,
                                    chunk.text,
                                    json.dumps(meta, ensure_ascii=False),
                                )
                            )
                        failures["successful_pdf_files"] += 1
                        pdf_status[doc_id] = {
                            "status": "indexed",
                            "size": size,
                            "chars": len(content),
                            "chunk_count": len(chunks),
                        }
                    else:
                        failures["failed_pdf_files"].append(f"{pdf_path}: No meaningful text extracted")
                        pdf_status[str(pdf_path)] = {
                            "status": "failed_extract",
                            "size": size,
                        }
                except Exception as e:
                    failures["failed_pdf_files"].append(f"{pdf_path}: {str(e)}")
                    pdf_status[str(pdf_path)] = {
                        "status": "error",
                        "error": str(e)[:120],
                    }
    article_categories = [category] if category else list(articles_config.keys())
    for cat in article_categories:
        articles = articles_config.get(cat)
        if not isinstance(articles, list):
            continue
        for article in articles:
            article_name = article["name"]
            pdf_file = Path(base_path) / cat / f"{article_name}.pdf"
            if not pdf_file.exists():
                failures["skipped_articles"].append(f"{cat}/{article_name}")
                continue
            if tika_ready or pdf_fallback_available:
                try:
                    pdf_candidate_count += 1
                    content, success = process_pdf_with_fallback(pdf_file, article_info=article)
                    if success and content:
                        doc_id = f"journal_articles/{cat}/{article_name}"
                        metadata = (
                            f"Title: {article['description']}\n"
                            f"Source: {article.get('url', 'Unknown')}\nType: Journal Article\n\n"
                        )
                        full_content = metadata + content
                        if summary_generator is not None and summary_stats["enabled"] and doc_id not in summarized_docs:
                            summary_stats["requests"] += 1
                            summary_payload = None
                            failed_due_to_exception = False
                            try:
                                summary_payload = summary_generator.summarize(
                                    doc_id=doc_id,
                                    content=full_content,
                                    repo_name=cat,
                                    repo_readme=None,
                                    repo_readme_path=None,
                                    metadata={"category": cat, "source": "journal_pdf", "article": article_name},
                                )
                            except Exception as exc:
                                failed_due_to_exception = True
                                summary_stats["failures"] += 1
                                logger.warning("Summary generation failed for %s: %s", doc_id, exc)
                            if summary_payload is not None:
                                summary_stats["responses"] += 1
                                if summary_payload.cached:
                                    summary_stats["cached_hits"] += 1
                                summary_meta = {
                                    "source_document": doc_id,
                                    "category": cat,
                                    "doc_type": "summary",
                                    "model": summary_payload.model,
                                    "cached": summary_payload.cached,
                                }
                                if summary_payload.repo_readme_path:
                                    summary_meta["repo_readme_path"] = summary_payload.repo_readme_path
                                summary_documents.append(
                                    (
                                        f"summaries/{doc_id}",
                                        summary_payload.summary,
                                        json.dumps(summary_meta, ensure_ascii=False),
                                    )
                                )
                                auto_model_weights[doc_id] = summary_payload.weight
                                summarized_docs.add(doc_id)
                            elif not failed_due_to_exception:
                                summary_stats["failures"] += 1
                        document = Document(path=pdf_file, content=full_content, metadata={"doc_id": doc_id})
                        chunks = pipeline.chunk_documents([document], config=chunk_config)
                        if not chunks:
                            logger.debug(f"Skipping low-value journal PDF: {doc_id}")
                            failures["skipped_low_value"].append(doc_id)
                            continue
                        size_bytes = pdf_file.stat().st_size if pdf_file.exists() else 0
                        for chunk in chunks:
                            meta = dict(chunk.metadata)
                            meta.setdefault("article_name", article_name)
                            meta.setdefault("category", meta.get("category", "docs"))
                            meta.setdefault("pdf_size_bytes", size_bytes)
                            meta.setdefault("source_url", article.get("url"))
                            documents.append(
                                (
                                    chunk.chunk_id,
                                    chunk.text,
                                    json.dumps(meta, ensure_ascii=False),
                                )
                            )
                        failures["successful_pdf_files"] += 1
                        pdf_status[doc_id] = {
                            "status": "indexed",
                            "size": size_bytes,
                            "chars": len(content),
                            "chunk_count": len(chunks),
                        }
                    else:
                        failures["failed_pdf_files"].append(f"{pdf_file}: No meaningful text extracted")
                        pdf_status[str(pdf_file)] = {"status": "failed_extract"}
                except Exception as e:
                    failures["failed_pdf_files"].append(f"{pdf_file}: {str(e)}")
                    pdf_status[str(pdf_file)] = {
                        "status": "error",
                        "error": str(e)[:120],
                    }
            else:
                failures["failed_pdf_files"].append(f"{pdf_file}: No PDF processing available")
                pdf_status[str(pdf_file)] = {"status": "no_processing"}
    summary_stats["documents_added"] = len(summary_documents)
    failures["summary_stats"] = summary_stats
    if summary_documents:
        documents.extend(summary_documents)
    total_indexed_documents = len(documents)
    failures["indexed_document_count"] = total_indexed_documents
    failures["text_file_candidates"] = text_candidate_count
    failures["pdf_file_candidates"] = pdf_candidate_count
    if not documents:
        if not dry_run:
            if text_candidate_count or pdf_candidate_count:
                failures["fatal_errors"].append(
                    "No documents were indexed even though source files were discovered. "
                    "Check for upstream processing failures (e.g., summarization errors) in the logs."
                )
            else:
                failures["fatal_errors"].append(
                    "No documents were indexed because no eligible source files were found in the configured sources."
                )
        else:
            logger.info("Dry run: no documents would be indexed.")
    elif not dry_run:
        logger.info(f"Indexing {len(documents)} documents...")
        logger.info("Building general embeddings index… (first run may download embedding model weights)")
        start = time.time()
        general_embeddings.index(documents)
        logger.info(f"General index built in {time.time() - start:.2f}s")
        general_embeddings.save(str(embeddings_dir / "index"))
        if use_dual_embedding and code_embeddings:
            logger.info("Building code embeddings index...")
            cstart = time.time()
            code_embeddings.index(documents)
            logger.info(f"Code index built in {time.time() - cstart:.2f}s")
            code_embeddings.save(str(embeddings_dir / "code_index"))
        results = general_embeddings.search("function", 3)
        logger.info("Test search results (general model):")
        for result in results:
            logger.info(f"  - {result['id']}: {result['text'][:100]}...")
        if use_dual_embedding and code_embeddings:
            code_results = code_embeddings.search("function", 3)
            logger.info("Test search results (code model):")
            for result in code_results:
                logger.info(f"  - {result['id']}: {result['text'][:100]}...")
    elif not documents:
        logger.warning("No documents found to index")
    # Write manifest
    if not dry_run:
        try:
            with open(embeddings_dir / "pdf_manifest.json", "w", encoding="utf-8") as mf:
                json.dump(pdf_status, mf, indent=2)
            logger.info(f"Wrote PDF manifest to {embeddings_dir / 'pdf_manifest.json'}")
        except Exception as e:
            logger.warning(f"Failed to write pdf_manifest.json: {e}")
        if auto_model_weights:
            try:
                with open(embeddings_dir / "auto_model_weights.json", "w", encoding="utf-8") as wf:
                    json.dump(auto_model_weights, wf, indent=2)
                logger.info(
                    f"Wrote suggested model weights for {len(auto_model_weights)} docs to"
                    f" {embeddings_dir / 'auto_model_weights.json'}"
                )
            except Exception as exc:
                logger.warning(f"Failed to write auto_model_weights.json: {exc}")
    if auto_model_weights:
        failures["auto_model_weights"] = auto_model_weights
    return failures


# --- Cleanup & summary functions (original) ---


def cleanup_pdf_articles(
    articles_config_path: str,
    base_path: str = "knowledge_base/raw",
    category: str = None,
) -> None:
    """Clean up downloaded PDF articles after embeddings are built"""
    logger = logging.getLogger(__name__)

    with open(articles_config_path, "r") as f:
        config = yaml.safe_load(f)

    categories = [category] if category else list(config.keys())
    for cat in categories:
        articles = config.get(cat)
        if not isinstance(articles, list):
            continue
        for article in articles:
            article_name = article["name"]
            pdf_file = Path(base_path) / cat / f"{article_name}.pdf"

            if pdf_file.exists():
                try:
                    pdf_file.unlink()
                    logger.info(f"Cleaned up PDF {cat}/{article_name}.pdf")
                except Exception as e:
                    logger.warning(f"Failed to clean up PDF {cat}/{article_name}.pdf: {e}")

    # Clean up empty category directories
    base_path_obj = Path(base_path)
    if base_path_obj.exists():
        for cat_dir in base_path_obj.iterdir():
            if cat_dir.is_dir() and not any(cat_dir.iterdir()):
                try:
                    cat_dir.rmdir()
                    logger.info(f"Cleaned up empty category directory: {cat_dir}")
                except Exception as e:
                    logger.warning(f"Failed to clean up empty category directory {cat_dir}: {e}")


def cleanup_raw_repositories(config_path: str, base_path: str = "knowledge_base/raw", category: str = None) -> None:
    """Clean up raw repositories after embeddings are built"""
    logger = logging.getLogger(__name__)

    with open(config_path, "r") as f:
        config = yaml.safe_load(f)

    categories = [category] if category else list(config.keys())
    for cat in categories:
        repos = config.get(cat)
        if not isinstance(repos, list):
            continue
        for repo in repos:
            repo_name = repo["name"]
            repo_dir = Path(base_path) / cat / repo_name

            if repo_dir.exists():
                try:
                    import shutil

                    shutil.rmtree(repo_dir)
                    logger.info(f"Cleaned up {cat}/{repo_name}")
                except Exception as e:
                    logger.warning(f"Failed to clean up {cat}/{repo_name}: {e}")

    # Clean up empty category directories
    base_path_obj = Path(base_path)
    if base_path_obj.exists():
        for cat_dir in base_path_obj.iterdir():
            if cat_dir.is_dir() and not any(cat_dir.iterdir()):
                try:
                    cat_dir.rmdir()
                    logger.info(f"Cleaned up empty category directory: {cat_dir}")
                except Exception as e:
                    logger.warning(f"Failed to clean up empty category directory {cat_dir}: {e}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Build the knowledge base by cloning repositories, downloading PDFs, and creating txtai embeddings."
    )
    parser.add_argument(
        "--config",
        default="config/repositories.yml",
        help="Path to repository configuration file",
    )
    parser.add_argument(
        "--articles-config",
        default=None,
        help="Path to PDF articles configuration file (optional)",
    )
    parser.add_argument(
        "--base-path",
        default="knowledge_base/raw",
        help="Base path for repositories and PDFs",
    )
    parser.add_argument(
        "--embeddings-path",
        default="knowledge_base/embeddings",
        help="Path for embeddings index",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without making changes",
    )
    parser.add_argument("--category", help="Process only a specific category")
    parser.add_argument(
        "--force-update",
        action="store_true",
        help="Update repositories and re-download PDFs if they already exist",
    )
    parser.add_argument(
        "--dirty",
        action="store_true",
        help="Leave the raw repos and PDFs in place after embeddings are built",
    )
    parser.add_argument(
        "--summaries",
        dest="summaries",
        action="store_true",
        default=DEFAULT_SUMMARIES_ENABLED,
        help="Generate Anthropic summaries for each document (requires ANTHROPIC_API_KEY)",
    )
    parser.add_argument(
        "--no-summaries",
        dest="summaries",
        action="store_false",
        help="Disable summary generation even if ENABLE_DOC_SUMMARIES is set",
    )

    args = parser.parse_args()

    if "build_pipeline" not in globals():

        def print_pipeline_summary(all_failures: dict, dry_run: bool = False) -> None:
            logger = logging.getLogger(__name__)
            prefix = "[DRY RUN] " if dry_run else ""
            logger.info("=" * 60)
            logger.info(f"{prefix}KNOWLEDGE BASE PIPELINE SUMMARY")
            logger.info("=" * 60)
            repo_failures = all_failures.get("repos", {})
            if repo_failures:
                logger.info("\n📁 REPOSITORIES:")
                if repo_failures.get("successful_clones"):
                    logger.info(f"  ✅ Successfully cloned: {len(repo_failures['successful_clones'])}")
                if repo_failures.get("successful_updates"):
                    logger.info(f"  🔄 Successfully updated: {len(repo_failures['successful_updates'])}")
                if repo_failures.get("skipped_existing"):
                    logger.info(f"  ⏭️  Skipped (already exists): {len(repo_failures['skipped_existing'])}")
                if repo_failures.get("failed_clones"):
                    logger.info(f"  ❌ Failed to clone: {len(repo_failures['failed_clones'])}")
                if repo_failures.get("failed_updates"):
                    logger.info(f"  ❌ Failed to update: {len(repo_failures['failed_updates'])}")
            article_failures = all_failures.get("articles", {})
            if article_failures:
                logger.info("\n📚 PDF ARTICLES:")
                if article_failures.get("successful_downloads"):
                    logger.info(f"  ✅ Successfully downloaded: {len(article_failures['successful_downloads'])}")
                if article_failures.get("skipped_existing"):
                    logger.info(f"  ⏭️  Skipped (already exists): {len(article_failures['skipped_existing'])}")
                if article_failures.get("failed_downloads"):
                    logger.info(f"  ❌ Failed to download: {len(article_failures['failed_downloads'])}")
            indexing_failures = all_failures.get("indexing", {}) or {}
            if indexing_failures:
                logger.info("\n🔍 INDEXING & EMBEDDING:")
                logger.info(
                    f"  ✅ Successfully indexed text files: {indexing_failures.get('successful_text_files', 0)}"
                )
                logger.info(f"  ✅ Successfully indexed PDF files: {indexing_failures.get('successful_pdf_files', 0)}")
                if indexing_failures.get("indexed_document_count") is not None:
                    logger.info(f"  📄 Indexed document chunks: {indexing_failures.get('indexed_document_count', 0)}")
                if indexing_failures.get("text_file_candidates") or indexing_failures.get("pdf_file_candidates"):
                    logger.info(
                        "  🔎 Source candidates — text: "
                        f"{indexing_failures.get('text_file_candidates', 0)}, "
                        f"PDF: {indexing_failures.get('pdf_file_candidates', 0)}"
                    )
                if indexing_failures.get("failed_text_files"):
                    logger.info(f"  ❌ Failed text files: {len(indexing_failures['failed_text_files'])}")
                if indexing_failures.get("skipped_articles"):
                    logger.info(f"  ⏭️  Skipped articles: {len(indexing_failures['skipped_articles'])}")
                if indexing_failures.get("failed_pdf_files"):
                    logger.info(f"  ❌ Failed PDF files: {len(indexing_failures['failed_pdf_files'])}")
                if indexing_failures.get("fatal_errors"):
                    for err in indexing_failures["fatal_errors"]:
                        logger.error(f"  🚫 Fatal: {err}")
                summary_stats = indexing_failures.get("summary_stats")
                if summary_stats:
                    logger.info("\n🧠 LLM SUMMARIES:")
                    configured = summary_stats.get("configured", False)
                    enabled = summary_stats.get("enabled", False)
                    if configured:
                        status_icon = "✅" if enabled else "⛔️"
                        logger.info(f"  {status_icon} Summaries enabled: {enabled}")
                    else:
                        logger.info("  ⏸️  Summaries disabled (flag not set)")
                    if enabled:
                        logger.info(f"  📨 Summary requests: {summary_stats.get('requests', 0)}")
                        logger.info(f"  📝 Summaries returned: {summary_stats.get('responses', 0)}")
                        if summary_stats.get("cached_hits"):
                            logger.info(f"  ♻️ Cached hits: {summary_stats.get('cached_hits', 0)}")
                        if summary_stats.get("failures"):
                            logger.info(f"  ❌ Summary failures: {summary_stats.get('failures', 0)}")
                        logger.info(f"  📦 Summary documents added: {summary_stats.get('documents_added', 0)}")
                    elif configured:
                        logger.info("  ℹ️  Summaries configured but disabled (check ANTHROPIC_API_KEY or permissions).")
            total_failures = (
                sum(len(v) for k, v in indexing_failures.items() if k.startswith("failed"))
                + len(indexing_failures.get("fatal_errors", []))
                + len(article_failures.get("failed_downloads", []))
            )
            logger.info("\n" + "=" * 60)
            if total_failures == 0:
                logger.info(f"{prefix}✅ PIPELINE COMPLETED SUCCESSFULLY - No failures detected!")
            else:
                logger.info(f"{prefix}⚠️  PIPELINE COMPLETED WITH {total_failures} FAILURES")
            logger.info("=" * 60)

        def build_pipeline(
            config_path: str,
            articles_config_path: str = None,
            base_path: str = "knowledge_base/raw",
            embeddings_path: str = "knowledge_base/embeddings",
            dry_run: bool = False,
            category: str = None,
            force_update: bool = False,
            dirty: bool = False,
            summaries: bool = False,
        ) -> None:
            logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
            logger = logging.getLogger(__name__)
            all_failures = {"repos": {}, "articles": {}, "indexing": {}}
            summary_generator = None
            if summaries:
                cache_dir = Path(embeddings_path).parent / "cache" / "summaries"
                summary_generator = SummaryGenerator(cache_dir=cache_dir, enabled=True)
            emit_progress(5, stage="start", detail="Cloning repositories")
            all_failures["repos"] = clone_repositories(config_path, base_path, dry_run, category, force_update)

            emit_progress(25, stage="repos_done", detail="Repositories cloned/updated")
            if articles_config_path and os.path.exists(articles_config_path):
                emit_progress(30, stage="articles", detail="Downloading PDF articles")
                all_failures["articles"] = download_pdf_articles(
                    articles_config_path, base_path, dry_run, category, force_update
                )
                emit_progress(50, stage="articles_done", detail="PDF articles downloaded")
            all_failures["indexing"] = build_txtai_index(
                config_path,
                articles_config_path,
                base_path,
                embeddings_path,
                dry_run,
                category,
                summary_generator,
            )
            emit_progress(85, stage="indexing_done", detail="Indexing completed")
            if not dirty and not dry_run:
                cleanup_raw_repositories(config_path, base_path, category)
                if articles_config_path and os.path.exists(articles_config_path):
                    cleanup_pdf_articles(articles_config_path, base_path, category)
            emit_progress(95, stage="cleanup", detail="Cleaning up raw files")
            print_pipeline_summary(all_failures, dry_run)
            if not dry_run:
                indexing_failures = all_failures.get("indexing") or {}
                fatal_errors = indexing_failures.get("fatal_errors") or []
                if fatal_errors:
                    for msg in fatal_errors:
                        logger.error(msg)
                    sys.exit(1)
                failed_texts = indexing_failures.get("failed_text_files") or []
                failed_pdfs = indexing_failures.get("failed_pdf_files") or []
                if failed_texts or failed_pdfs:
                    logger.warning(
                        "Indexing completed with failures. See log output for details on the affected files."
                    )
            emit_progress(100, stage="done", detail="Pipeline finished")

    build_pipeline(
        config_path=args.config,
        articles_config_path=args.articles_config,
        base_path=args.base_path,
        embeddings_path=args.embeddings_path,
        dry_run=args.dry_run,
        category=args.category,
        force_update=args.force_update,
        dirty=args.dirty,
        summaries=args.summaries,
    )
