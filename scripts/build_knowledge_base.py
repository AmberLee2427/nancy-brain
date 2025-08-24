"""
This script processes all repositories in the config/repositories.yml file.
Orchestrates the full knowledge base build pipeline (cloning, direct txtai indexing).
"""

import os

os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

import yaml
import subprocess
from pathlib import Path
import logging
import argparse
import requests

# Optional imports
try:
    from nb4llm import convert_ipynb_to_txt
except ImportError:
    convert_ipynb_to_txt = None

# Fix OpenMP issue before importing any ML libraries
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

# Add import for direct Tika PDF processing
try:
    import tika
    from tika import parser as tika_parser

    TIKA_AVAILABLE = True
except ImportError:
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


def is_excluded_pdf(path: str) -> bool:
    p = str(path)
    return any(token in p for token in EXCLUDE_PDF_SUBSTRINGS)


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
    if TIKA_AVAILABLE and not tika_ready and not os.environ.get("SKIP_PDF_PROCESSING", "").lower() == "true":
        try:
            os.environ.setdefault("TIKA_CLIENT_TIMEOUT", "60")
            os.environ.setdefault("TIKA_SERVER_TIMEOUT", "60")
            os.environ.setdefault("TIKA_STARTUP_TIMEOUT", "120")
            tika.initVM()
            tika_ready = True
            logger.info("✅ Tika VM initialized (lazy) for PDF processing")
        except Exception as e:
            logger.warning(f"Failed lazy Tika init: {e}")
    if TIKA_AVAILABLE and tika_ready and not os.environ.get("SKIP_PDF_PROCESSING", "").lower() == "true":
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
    path = Path(doc_id)
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
    if TIKA_AVAILABLE and not tika_ready and not os.environ.get("SKIP_PDF_PROCESSING", "").lower() == "true":
        try:
            os.environ.setdefault("TIKA_CLIENT_TIMEOUT", "60")
            os.environ.setdefault("TIKA_SERVER_TIMEOUT", "60")
            os.environ.setdefault("TIKA_STARTUP_TIMEOUT", "120")
            tika.initVM()
            tika_ready = True
            logger.info("✅ Tika VM initialized for PDF processing")
        except Exception as e:
            logger.warning(f"Failed to initialize Tika VM: {e}. Will use fallback methods if available.")
    with open(config_path, "r") as f:
        config = yaml.safe_load(f)
    articles_config = {}
    if articles_config_path and os.path.exists(articles_config_path):
        with open(articles_config_path, "r") as f:
            articles_config = yaml.safe_load(f)
        logger.info(f"Loaded articles configuration from {articles_config_path}")
    embeddings_dir = Path(embeddings_path)
    embeddings_dir.mkdir(parents=True, exist_ok=True)
    general_embeddings = Embeddings(
        {
            "path": "sentence-transformers/all-MiniLM-L6-v2",
            "content": True,
            "backend": "faiss",
        }
    )
    code_embeddings = None
    if use_dual_embedding:
        code_embeddings = Embeddings({"path": code_model, "content": True, "backend": "faiss"})
        logger.info(f"Initialized code embeddings with model: {code_model}")
    try:
        with open("config/index_weights.yaml", "r") as f:
            ext_weights = yaml.safe_load(f)
    except Exception:
        ext_weights = {}
    categories = [category] if category else list(config.keys())
    documents = []
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
    }
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
            if convert_ipynb_to_txt is not None:
                for ipynb_file in repo_dir.rglob("*.ipynb"):
                    nb_txt_file = ipynb_file.with_suffix(".nb.txt")
                    if not nb_txt_file.exists() or ipynb_file.stat().st_mtime > nb_txt_file.stat().st_mtime:
                        try:
                            convert_ipynb_to_txt(str(ipynb_file), str(nb_txt_file))
                            failures["successful_notebook_conversions"] += 1
                        except Exception as e:
                            failures["failed_notebook_conversions"].append(f"{ipynb_file}: {str(e)}")
            text_files = []
            for ext in [".py", ".md", ".txt", ".rst", ".yaml", ".yml", ".json"]:
                text_files.extend(repo_dir.rglob(f"*{ext}"))
            text_files.extend(repo_dir.rglob("*.nb.txt"))
            pdf_files = []
            if tika_ready:
                pdf_files.extend(repo_dir.rglob("*.pdf"))
            # Apply exclusions & size filter pre-read
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
            skip_dirs = {
                ".git",
                ".github",
                "__pycache__",
                "node_modules",
                ".pytest_cache",
                ".mypy_cache",
            }
            text_files = [f for f in text_files if not any(skip in f.parts for skip in skip_dirs)]
            pdf_files = [f for f in pdf_files if not any(skip in f.parts for skip in skip_dirs)]
            text_files = [f for f in text_files if "docs/build" not in str(f) and not str(f).endswith(".rst.txt")]
            for file_path in text_files:
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        content = f.read()
                    if not content.strip():
                        continue
                    doc_id = f"{cat}/{repo_name}/{file_path.relative_to(repo_dir)}"
                    documents.append((doc_id, content))
                    failures["successful_text_files"] += 1
                except Exception as e:
                    failures["failed_text_files"].append(f"{file_path}: {str(e)}")
            for pdf_path in pdf_files:
                try:
                    content, success = process_pdf_with_fallback(pdf_path, repo_info=repo)
                    size = pdf_path.stat().st_size if pdf_path.exists() else 0
                    if success and content:
                        doc_id = f"{cat}/{repo_name}/{pdf_path.relative_to(repo_dir)}"
                        metadata = f"Source: Repository PDF from {repo['url']}\nPath: {pdf_path.relative_to(repo_dir)}\nType: Repository Document\n\n"
                        full_content = metadata + content
                        documents.append((doc_id, full_content))
                        failures["successful_pdf_files"] += 1
                        pdf_status[doc_id] = {
                            "status": "indexed",
                            "size": size,
                            "chars": len(content),
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
                    content, success = process_pdf_with_fallback(pdf_file, article_info=article)
                    if success and content:
                        doc_id = f"journal_articles/{cat}/{article_name}"
                        metadata = f"Title: {article['description']}\nSource: {article.get('url', 'Unknown')}\nType: Journal Article\n\n"
                        full_content = metadata + content
                        documents.append((doc_id, full_content))
                        failures["successful_pdf_files"] += 1
                        pdf_status[doc_id] = {
                            "status": "indexed",
                            "size": pdf_file.stat().st_size if pdf_file.exists() else 0,
                            "chars": len(content),
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
    if documents and not dry_run:
        logger.info(f"Indexing {len(documents)} documents...")
        logger.info("Building general embeddings index...")
        general_embeddings.index(documents)
        general_embeddings.save(str(embeddings_dir / "index"))
        if use_dual_embedding and code_embeddings:
            logger.info("Building code embeddings index...")
            code_embeddings.index(documents)
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
            import json

            with open(embeddings_dir / "pdf_manifest.json", "w", encoding="utf-8") as mf:
                json.dump(pdf_status, mf, indent=2)
            logger.info(f"Wrote PDF manifest to {embeddings_dir / 'pdf_manifest.json'}")
        except Exception as e:
            logger.warning(f"Failed to write pdf_manifest.json: {e}")
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
        default="config/articles.yml",
        help="Path to PDF articles configuration file",
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
                if indexing_failures.get("skipped_articles"):
                    logger.info(f"  ⏭️  Skipped articles: {len(indexing_failures['skipped_articles'])}")
                if indexing_failures.get("failed_pdf_files"):
                    logger.info(f"  ❌ Failed PDF files: {len(indexing_failures['failed_pdf_files'])}")
            total_failures = sum(len(v) for k, v in indexing_failures.items() if k.startswith("failed")) + len(
                article_failures.get("failed_downloads", [])
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
        ) -> None:
            logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
            logger = logging.getLogger(__name__)
            all_failures = {"repos": {}, "articles": {}, "indexing": {}}
            all_failures["repos"] = clone_repositories(config_path, base_path, dry_run, category, force_update)
            if articles_config_path and os.path.exists(articles_config_path):
                all_failures["articles"] = download_pdf_articles(
                    articles_config_path, base_path, dry_run, category, force_update
                )
            all_failures["indexing"] = build_txtai_index(
                config_path,
                articles_config_path,
                base_path,
                embeddings_path,
                dry_run,
                category,
            )
            if not dirty and not dry_run:
                cleanup_raw_repositories(config_path, base_path, category)
                if articles_config_path and os.path.exists(articles_config_path):
                    cleanup_pdf_articles(articles_config_path, base_path, category)
            print_pipeline_summary(all_failures, dry_run)

    build_pipeline(
        config_path=args.config,
        articles_config_path=args.articles_config,
        base_path=args.base_path,
        embeddings_path=args.embeddings_path,
        dry_run=args.dry_run,
        category=args.category,
        force_update=args.force_update,
        dirty=args.dirty,
    )
