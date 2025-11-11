# Nancy Brain

[Pages](https://amberlee2427.github.io/nancy-brain/) [Read the Docs](https://nancy-brain.readthedocs.io/en/latest/)

**Turn any GitHub repository into a searchable knowledge base for AI agents.**

Load the complete source code, documentation, examples, and notebooks from any package you're working with. Nancy Brain gives AI assistants instant access to:

- **Full source code** - actual Python classes, methods, implementation details
- **Live documentation** - tutorials, API docs, usage examples  
- **Real examples** - Jupyter notebooks, test cases, configuration files
- **Smart weighting** - boost important docs, learning persists across sessions

The AI can now answer questions like "How do I initialize this class?" or "Show me an example of fitting a light curve" with actual code from the repositories you care about.

## 🚀 Quick Start

```bash
# Install anywhere
pip install nancy-brain

# Initialize a new project
nancy-brain init my-ai-project
cd my-ai-project

# Add some repositories  
nancy-brain add-repo https://github.com/scikit-learn/scikit-learn.git

# Build the knowledge base
nancy-brain build

# Search it!
nancy-brain search "machine learning algorithms"

# Or launch the web interface
nancy-brain ui
```

## 🌐 Web Admin Interface

Launch the visual admin interface for easy knowledge base management:

```bash
nancy-brain ui
```

Features:
- **🔍 Live Search** - Test your knowledge base with instant results
- **📚 Repository Management** - Add/remove GitHub repos with visual forms
- **📄 Article Management** - Add/remove PDF articles with visual forms
- **🏗️ Build Control** - Trigger knowledge base builds with options
- **📊 System Status** - Check embeddings, configuration, and health

Perfect for non-technical users and rapid prototyping!

## 🖥️ Command Line Interface

```bash
nancy-brain init <project>        # Initialize new project
nancy-brain add-repo <url>        # Add GitHub repositories  
nancy-brain add-article <url> <name>  # Add PDF articles
nancy-brain add-new-user <user> <pass>  # Create login credentials
nancy-brain build                 # Build knowledge base
nancy-brain search "query"        # Search knowledge base
nancy-brain serve                 # Start HTTP API server
nancy-brain ui                    # Launch web admin interface
```


### Chunking

Nancy Brain uses the [`chunky-files`](https://pypi.org/project/chunky-files/) package for chunking repositories. Configure chunk boundaries with environment variables before running a build:

| Variable | Purpose | Default |
| --- | --- | --- |
| `CHUNKY_LINES_PER_CHUNK` | Maximum lines per chunk window | 80 |
| `CHUNKY_LINE_OVERLAP` | Overlap between consecutive chunks | 10 |
| `CHUNKY_MAX_CHARS` | Maximum characters per chunk | 2000 |

To adjust chunks per file programmatically, supply a custom `ChunkerConfig` through the build pipeline. For advanced semantic chunkers (Tree-sitter, language-specific splits), install extras: `pip install chunky-files[tree]`.

### Optional: Anthropic-powered summaries

Set an API key and opt-in to generate document-level summaries and suggested search weights during a build:

```bash
export ANTHROPIC_API_KEY="sk-ant-..."
export ENABLE_DOC_SUMMARIES=true   # or pass --summaries on the build command
nancy-brain build --summaries
```

Summaries are cached under `knowledge_base/cache/summaries/` using the document content hash, so reruns only
call Anthropic when files change. Suggested weights are written to `knowledge_base/embeddings/auto_model_weights.json`
for review before merging into your active `model_weights.yml`.

## Technical Architecture

A lightweight Retrieval-Augmented Generation (RAG) knowledge base with:
- Embedding + search pipeline (txtai / FAISS based)
- HTTP API connector (FastAPI)
- Model Context Protocol (MCP) server connector (tools for search / retrieve / tree / weight)
- Dynamic weighting system (extension/path weights + runtime doc preferences)

Designed to power AI assistants on Slack, IDEs, Claude Desktop, custom GPTs, and any MCP-capable client.

---
## 1. Installation & Quick Setup

### For Users (Recommended)
```bash
# Install the package
pip install nancy-brain

# Initialize a new project
nancy-brain init my-knowledge-base
cd my-knowledge-base

# Add repositories and build
nancy-brain add-repo https://github.com/your-org/repo.git
nancy-brain add-article "https://arxiv.org/pdf/paper.pdf" "paper_name" --description "Important paper"
nancy-brain build

# Launch web interface
nancy-brain ui
```

### For Developers
```bash
# Clone and install in development mode
git clone <repo-url>
cd nancy-brain
pip install -e ."[dev]"

# Test installation
pytest -q
nancy-brain --help
```

Note for developers: The build pipeline now requires `docutils` and `pylatexenc` to reliably convert
reStructuredText (`.rst`) and LaTeX (`.tex`) files to plain text. These are included in the project's
dependencies (`pyproject.toml`) so `pip install -e ."[dev]"` will install them automatically. If you
prefer to install them manually in your environment, run:

```bash
pip install docutils pylatexenc
```

Developer note (CLI & tests):
The CLI commands and `RAGService` avoid importing heavy ML libraries (such as `txtai` and `torch`) at
module import time. The service defers initializing the embedding `Search` until an embeddings index is
present or a command explicitly needs it. This makes running CLI help and most unit tests fast and safe
in minimal environments. If a test needs a functioning `Search`, mock `rag_core.search` (insert a
dummy module into `sys.modules['rag_core.search']`) before instantiating `RAGService`.

---
## 2. Project Layout (Core Parts)
```
nancy_brain/                    # Main Python package
├── cli.py                      # Command line interface
├── admin_ui.py                 # Streamlit web admin interface
└── __init__.py                 # Package initialization

connectors/http_api/app.py      # FastAPI app
connectors/mcp_server/          # MCP server implementation
rag_core/                       # Core service, search, registry, store, types
scripts/                        # KB build & management scripts
config/repositories.yml         # Source repository list (input KB)
config/weights.yaml             # Extension + path weighting config
config/model_weights.yaml       # (Optional) static per-doc multipliers
```

---
## 3. Configuration

### 3.1 Repositories (`config/repositories.yml`)
Structure (categories map to lists of repos):
```yaml
<category_name>:
  - name: repoA
    url: https://github.com/org/repoA.git
  - name: repoB
    url: https://github.com/org/repoB.git
```
Categories become path prefixes inside the knowledge base (e.g. `cat1/repoA/...`).

### 3.2 Weight Config (`config/weights.yaml`)
- `extensions`: base multipliers by file extension (.py, .md, etc.)
- `path_includes`: if substring appears in doc_id, multiplier is applied multiplicatively.

### 3.3 Model Weights (`config/model_weights.yaml`)
Optional static per-document multipliers (legacy / seed). Runtime updates via `/weight` endpoint or MCP `set_weight` tool override or augment in-memory weights.

### 3.4 Environment Variables
Common knobs you can export (or place in `config/.env`) to tune builds and the admin UI:

| Var | Purpose | Default / Typical |
|-----|---------|-------------------|
| `KMP_DUPLICATE_LIB_OK` | Avoid OpenMP clashes on macOS | TRUE |
| `USE_DUAL_EMBEDDING` | Enable dual (text + code) embedding scoring | true |
| `CODE_EMBEDDING_MODEL` | Code embedding model when dual mode enabled | microsoft/codebert-base |
| `NB_TEXT_EMBEDDING_MODEL` | Override text embedding model path | sentence-transformers/all-MiniLM-L6-v2 |
| `NB_CODE_EMBEDDING_MODEL` | Override code embedding model path | inherits `CODE_EMBEDDING_MODEL` |
| `SKIP_PDF_PROCESSING` | Skip PDF downloads/extraction during build | false |
| `ANTHROPIC_API_KEY` | Enable Anthropic summaries (used with `--summaries`) | unset |
| `ENABLE_DOC_SUMMARIES` | Toggle summaries in builds by default | false |
| `NB_SUMMARY_TIMEOUT_SECONDS` | Per-doc summary timeout | 25 |
| `NB_PER_FILE_LOG` | Log each file’s chunk count (diagnostics) | false |
| `NB_SKIP_TEST_SEARCH` | Skip post-build sample queries | false |
| `NB_SECRET_KEY` | JWT signing key for API/UI auth | dev key (change in prod) |
| `NB_JWT_ALGORITHM` | JWT algorithm | HS256 |
| `NB_ACCESS_EXPIRE_MINUTES` | Access token lifetime | 60 |
| `NB_REFRESH_EXPIRE_MINUTES` | Refresh token lifetime | 1440 |
| `NB_USERS_DB` | SQLite users DB path | users.db |
| `OMP_NUM_THREADS` / `MKL_NUM_THREADS` / `NUMEXPR_MAX_THREADS` | Cap CPU threading for heavy libs | unset |
| `TOKENIZERS_PARALLELISM` | Suppress HF tokenizer warning | false |

> Tip: First builds download Hugging Face models; set `NB_TEXT_EMBEDDING_MODEL` to a local path (or run a quick `python - <<'PY' …` prefetch) if your network is slow.

### Creating login users

Nancy Brain’s HTTP API and Streamlit UI expect credentials stored in `NB_USERS_DB` (default `users.db`).  
Use the CLI to add hashed logins without touching the database directly:

```bash
nancy-brain add-new-user <username> <password>
```

The command bootstraps the auth tables (if they do not exist), hashes the password with `passlib`, and saves the record in the configured SQLite file.  
Point `NB_USERS_DB` to a shared path before running the command if you need a centralized user store.

---
## 4. Building the Knowledge Base
Embeddings must be built before meaningful search.

### Using the CLI (Recommended)
```bash
# Basic build (repositories only)
nancy-brain build

# Build with PDF articles (if configured)
nancy-brain build --articles-config config/articles.yml

# Force update all repositories
nancy-brain build --force-update

# Or use the web interface
nancy-brain ui  # Go to "Build Knowledge Base" page
```

### Using the Python Script Directly
```bash
conda activate nancy-brain
cd src/nancy-brain
# Basic build (repositories only)
python scripts/build_knowledge_base.py \
  --config config/repositories.yml \
  --embeddings-path knowledge_base/embeddings

# Full build including optional PDF articles (if config/articles.yml exists)
python scripts/build_knowledge_base.py \
  --config config/repositories.yml \
  --articles-config config/articles.yml \
  --base-path knowledge_base/raw \
  --embeddings-path knowledge_base/embeddings \
  --force-update \
  --dirty
# You can run without the dirty tag to automatically 
# remove source material after indexing is complete
```
Run `python scripts/build_knowledge_base.py -h` for all options.

### 4.1 PDF Articles (Optional Quick Setup)
1. Create `config/articles.yml` (example):
```yaml
journal_articles:
  - name: Paczynski_1986_ApJ_304_1
    url: https://ui.adsabs.harvard.edu/link_gateway/1986ApJ...304....1P/PUB_PDF
    description: Paczynski (1986) – Gravitational microlensing
```
2. Install Java (for Tika PDF extraction) – macOS:
```bash
brew install openjdk
export JAVA_HOME="/opt/homebrew/opt/openjdk"
export PATH="$JAVA_HOME/bin:$PATH"
```
3. (Optional fallback only) Install lightweight PDF libs if you skip Java:
```bash
pip install PyPDF2 pdfplumber
```
4. Build with articles (explicit):
```bash
python scripts/build_knowledge_base.py --config config/repositories.yml --articles-config config/articles.yml
```
5. Keep raw PDFs for inspection: add `--dirty`.

Notes:
- If Java/Tika not available, script attempts fallback extraction (needs PyPDF2/pdfplumber or fitz).
- Cleanups remove raw PDFs unless `--dirty` supplied.
- Article docs are indexed under `journal_articles/<category>/<name>`.

Key flags:
- `--config` path to repositories YAML (was --repositories in older docs)
- `--articles-config` optional PDF articles YAML
- `--base-path` where raw repos/PDFs live (default knowledge_base/raw)
- `--embeddings-path` output index directory
- `--force-update` re-pull repos / re-download PDFs
- `--category <name>` limit to one category
- `--dry-run` show actions without performing
- `--dirty` keep raw sources (skip cleanup)

This will:
1. Clone / update listed repos under `knowledge_base/raw/<category>/<repo>`
2. (Optionally) download PDFs into category directories
3. Convert notebooks (*.ipynb -> *.nb.txt) if nb4llm available
4. Extract and normalize text + (optionally) PDF text
5. Build / update embeddings index at `knowledge_base/embeddings` (and `code_index` if dual embeddings enabled)

Re-run when repositories or articles change.

---
## 5. Running Services

### Web Admin Interface (Recommended for Getting Started)
```bash
nancy-brain ui
# Opens Streamlit interface at http://localhost:8501
# Features: search, repo management, build control, status
```

### HTTP API Server
```bash
# Using CLI
nancy-brain serve

# Or directly with uvicorn
uvicorn connectors.http_api.app:app --host 0.0.0.0 --port 8000
```

### MCP Server (for AI Assistants)
```bash
# Run MCP stdio server
python run_mcp_server.py
```

Initialize service programmatically (example pattern):
```python
from pathlib import Path
from connectors.http_api.app import initialize_rag_service
initialize_rag_service(
    config_path=Path('config/repositories.yml'),
    embeddings_path=Path('knowledge_base/embeddings'),
    weights_path=Path('config/weights.yaml'),
    use_dual_embedding=True
)
```
The FastAPI dependency layer will then serve requests.

### Command Line Search
```bash
# Quick search from command line
nancy-brain search "machine learning algorithms" --limit 5

# Search with custom paths
nancy-brain search "neural networks" \
  --embeddings-path custom/embeddings \
  --config custom/repositories.yml
```

### 5.1 Endpoints (Bearer auth placeholder)
| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Service status |
| GET | `/version` | Index / build meta |
| GET | `/search?query=...&limit=N` | Search documents |
| POST | `/retrieve` | Retrieve passage (doc_id + line range) |
| POST | `/retrieve/batch` | Batch retrieve |
| GET | `/tree?prefix=...` | List KB tree |
| POST | `/weight` | Set runtime doc weight |

Example:
```bash
curl -H "Authorization: Bearer TEST" 'http://localhost:8000/search?query=light%20curve&limit=5'
```

## Admin UI Authentication

The Streamlit admin UI supports HTTP API authentication (recommended) and a
convenience insecure bypass for local development.

- To use the HTTP API for auth, ensure your API is running and set `NB_API_URL` if not using the default:

```bash
export NB_API_URL="http://localhost:8000"
streamlit run nancy_brain/admin_ui.py
```

- For local development without an API, enable an insecure bypass (only use locally):

```bash
export NB_ALLOW_INSECURE=true
streamlit run nancy_brain/admin_ui.py
```

The admin UI stores the access token and refresh token in `st.session_state` for the current Streamlit session.

Set a document weight (boost factor 0.5–2.0 typical):
```bash
curl -X POST -H 'Authorization: Bearer TEST' \
  -H 'Content-Type: application/json' \
  -d '{"doc_id":"cat1/repoA/path/file.py","multiplier":2.0}' \
  http://localhost:8000/weight
```

---
## 6. MCP Server
Run the MCP stdio server:
```bash
python run_mcp_server.py
```
Tools exposed (operation names):
- `search` (query, limit)
- `retrieve` (doc_id, start, end)
- `retrieve_batch`
- `tree` (prefix, depth)
- `set_weight` (doc_id, multiplier)
- `status` / `version`

### 6.1 VS Code Integration
1. Install a Model Context Protocol client extension (e.g. "MCP Explorer" or equivalent).
2. Add a server entry pointing to the script, stdio transport. Example config snippet:
```
{
  "mcpServers": {
    "nancy-brain": {
      "command": "python",
      "args": ["/absolute/path/to/src/nancy-brain/run_mcp_server.py"],
      "env": {
        "PYTHONPATH": "/absolute/path/to/src/nancy-brain" 
      }
    }
  }
}
```

*Specific mamba environment example:*

```
{
	"servers": {
		"nancy-brain": {
			"type": "stdio",
			"command": "/Users/malpas.1/.local/share/mamba/envs/nancy-brain/bin/python",
			"args": [
				"/Users/malpas.1/Code/slack-bot/src/nancy-brain/run_mcp_server.py"
			],
			"env": {
				"PYTHONPATH": "/Users/malpas.1/Code/slack-bot/src/nancy-brain",
				"KMP_DUPLICATE_LIB_OK": "TRUE"
			}
		}
	},
	"inputs": []
}
```

3. Reload VS Code. The provider should list the tools; invoke `search` to test.

### 6.2 Claude Desktop
Claude supports MCP config in its settings file. Add an entry similar to above (command + args). Restart Claude Desktop; tools appear in the prompt tools menu.

---
## 7. Use Cases & Examples

### For Researchers
```bash
# Add astronomy packages
nancy-brain add-repo https://github.com/astropy/astropy.git
nancy-brain add-repo https://github.com/rpoleski/MulensModel.git

# Add key research papers
nancy-brain add-article \
  "https://ui.adsabs.harvard.edu/link_gateway/1986ApJ...304....1P/PUB_PDF" \
  "Paczynski_1986_microlensing" \
  --category "foundational_papers" \
  --description "Paczynski (1986) - Gravitational microlensing by the galactic halo"

nancy-brain build

# AI can now answer: "How do I model a microlensing event?"
nancy-brain search "microlensing model fit"
```

### For ML Engineers  
```bash
# Add ML frameworks
nancy-brain add-repo https://github.com/scikit-learn/scikit-learn.git
nancy-brain add-repo https://github.com/pytorch/pytorch.git
nancy-brain build

# AI can now answer: "Show me gradient descent implementation"
nancy-brain search "gradient descent optimizer"
```

### For Teams
```bash
# Launch web interface for non-technical users
nancy-brain ui
# Point team to http://localhost:8501
# They can search, add repos, manage articles, trigger builds visually
# Repository Management tab: Add GitHub repos
# Articles tab: Add PDF papers and documents
```

---
## 8. Slack Bot (Nancy)
The Slack-facing assistant lives outside this submodule (see parent repository). High-level steps:
1. Ensure HTTP API running and reachable (or embed service directly in bot process).
2. Bot receives user message -> constructs query -> calls `/search` and selected `/retrieve` for context.
3. Bot composes answer including source references (doc_id and GitHub URL) before sending back.
4. Optional: adaptively call `/weight` when feedback indicates a source should be boosted or dampened.

Check root-level `nancy_bot.py` or Slack integration docs (`SLACK.md`) for token setup and event subscription details.

---
## 9. Custom GPT (OpenAI Actions / Function Calls)
Define OpenAI tool specs mapping to HTTP endpoints:
- `searchDocuments(query, limit)` -> GET /search
- `retrievePassage(doc_id, start, end)` -> POST /retrieve
- `listTree(prefix, depth)` -> GET /tree
- `setWeight(doc_id, multiplier)` -> POST /weight

Use an API gateway or direct URL. Include auth header. Provide JSON schemas matching request/response models.

---
## 10. Dynamic Weighting Flow
1. Base score from embeddings (dual or single).
2. Extension multiplier (from weights.yaml).
3. Path multiplier(s) (cumulative).
4. Model weight (static config + runtime overrides via `/weight`).
5. Adjusted score = base * extension_weight * model_weight (and any path multipliers folded into extension weight step).

Runtime `/weight` takes effect immediately on subsequent searches.

---
## 11. Updating / Rebuilding
| Action | Command |
|--------|---------|
| Pull repo updates | `nancy-brain build --force-update` or re-run build script |
| Change extension weights | Edit `config/weights.yaml` (no restart needed for runtime? restart or rebuild if cached) |
| Change embedding model | Delete / rename existing `knowledge_base/embeddings` and rebuild with new env vars |

---
## 12. Deployment Notes
- Containerize: build image with pre-built embeddings baked or mount a persistent volume.
- Health probe: `/health` (returns 200 once rag_service initialized) else 503.
- Concurrency: FastAPI async safe; weight updates are simple dict writes (low contention). For heavy load consider a lock if races appear.
- Persistence of runtime weights: currently in-memory; persist manually if needed (extend `set_weight`).

---
## 13. Troubleshooting
| Symptom | Cause | Fix |
|---------|-------|-----|
| 503 RAG service not initialized | `initialize_rag_service` not called / wrong paths | Call initializer with correct embeddings path |
| Empty search results | Embeddings not built / wrong path | Re-run `nancy-brain build`, verify index directory |
| macOS OpenMP crash | MKL / libomp duplicate | `KMP_DUPLICATE_LIB_OK=TRUE` already set early |
| MCP tools not visible | Wrong path or PYTHONPATH | Use absolute paths in MCP config |
| CLI command not found | Package not installed | `pip install nancy-brain` |

Enable debug logging:
```bash
export LOG_LEVEL=DEBUG
```
(add logic or run with `uvicorn --log-level debug`)

---
## 14. Development & Contributing
```bash
# Clone and set up development environment
git clone <repo-url>
cd nancy-brain
pip install -e ."[dev]"

# Run tests
pytest

# Run linting
black nancy_brain/ 
flake8 nancy_brain/

# Test CLI locally
nancy-brain --help
```

### Releasing
Nancy Brain uses automated versioning and PyPI publishing:

```bash
# Bump patch version (0.1.0 → 0.1.1)
./release.sh patch

# Bump minor version (0.1.0 → 0.2.0)  
./release.sh minor

# Bump major version (0.1.0 → 1.0.0)
./release.sh major
```

This automatically:
1. Updates version numbers in `pyproject.toml` and `nancy_brain/__init__.py`
2. Creates a git commit and tag
3. Pushes to GitHub, triggering PyPI publication via GitHub Actions

Manual version management:
```bash
# See current version and bump options
bump-my-version show-bump

# Dry run (see what would change)
bump-my-version bump --dry-run patch
```

---
## 15. Roadmap (Optional)
- Persistence layer for runtime weights
- Additional retrieval filters (e.g. semantic rerank)
- Auth plugin / token validation
- VS Code extension
- Package publishing to PyPI

---
## 16. License
See parent repository license.

---
## 17. Minimal Verification Script
```bash
# After build & run
curl -H 'Authorization: Bearer TEST' 'http://localhost:8000/health'
```
Expect JSON with status + trace_id.

---
Happy searching.

<br>
<br>
<br>
<br>

<!-- Badges Dashbord to check for issues, PRs, and health of CI tests and docs builds -->
[![GitHub license](https://img.shields.io/github/license/amberlee2427/nancy-brain)](https://github.com/amberlee2427/nancy-brain/blob/main/LICENSE) [![GitHub issues](https://img.shields.io/github/issues/amberlee2427/nancy-brain)](https://github.com/amberlee2427/nancy-brain/issues) [![GitHub releases](https://img.shields.io/github/releases/amberlee2427/nancy-brain)](https://github.com/amberlee2427/nancy-brain/releases) [![GitHub status](https://github.com/amberlee2427/nancy-brain/actions/workflows/ci.yml/badge.svg)](https://github.com/amberlee2427/nancy-brain/actions/workflows/ci.yml) [![docs status](https://github.com/amberlee2427/nancy-brain/actions/workflows/docs.yml/badge.svg)](https://github.com/amberlee2427/nancy-brain/actions/workflows/docs.yml)
