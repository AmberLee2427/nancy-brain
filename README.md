# Nancy Brain

**Turn any GitHub repository into a searchable knowledge base for AI agents.**

Load the complete source code, documentation, examples, and notebooks from any package you're working with. Nancy Brain gives AI assistants instant access to:

- **Full source code** - actual Python classes, methods, implementation details
- **Live documentation** - tutorials, API docs, usage examples  
- **Real examples** - Jupyter notebooks, test cases, configuration files
- **Smart weighting** - boost important docs, learning persists across sessions

The AI can now answer questions like "How do I initialize this class?" or "Show me an example of fitting a light curve" with actual code from the repositories you care about.

## Technical Architecture

A lightweight Retrieval-Augmented Generation (RAG) knowledge base with:
- Embedding + search pipeline (txtai / FAISS based)
- HTTP API connector (FastAPI)
- Model Context Protocol (MCP) server connector (tools for search / retrieve / tree / weight)
- Dynamic weighting system (extension/path weights + runtime doc preferences)

Designed to power AI assistants on Slack, IDEs, Claude Desktop, custom GPTs, and any MCP-capable client.

---
## 1. Quick Start

```bash
# From repo root (adjust path as needed)
cd src/nancy-brain

# (Recommended) create env
conda create -n nancy-brain python=3.12 -y
conda activate nancy-brain

# Install package (editable) + deps
pip install -e ."[dev]"
```

Test installation:
```bash
pytest -q
```
All tests should pass.

---
## 2. Project Layout (Core Parts)
```
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
| Var | Purpose | Default |
|-----|---------|---------|
| `USE_DUAL_EMBEDDING` | Enable dual (general + code) embedding scoring | true |
| `CODE_EMBEDDING_MODEL` | Model name for code index (if dual) | microsoft/codebert-base |
| `KMP_DUPLICATE_LIB_OK` | Set to TRUE to avoid OpenMP macOS clash | TRUE |

---
## 4. Building the Knowledge Base
Embeddings must be built before meaningful search.

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
## 5. Running the HTTP API

Development (auto-reload optional):
```bash
uvicorn connectors.http_api.app:app --host 0.0.0.0 --port 8000
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
## 7. Slack Bot (Nancy)
The Slack-facing assistant lives outside this submodule (see parent repository). High-level steps:
1. Ensure HTTP API running and reachable (or embed service directly in bot process).
2. Bot receives user message -> constructs query -> calls `/search` and selected `/retrieve` for context.
3. Bot composes answer including source references (doc_id and GitHub URL) before sending back.
4. Optional: adaptively call `/weight` when feedback indicates a source should be boosted or dampened.

Check root-level `nancy_bot.py` or Slack integration docs (`SLACK.md`) for token setup and event subscription details.

---
## 8. Custom GPT (OpenAI Actions / Function Calls)
Define OpenAI tool specs mapping to HTTP endpoints:
- `searchDocuments(query, limit)` -> GET /search
- `retrievePassage(doc_id, start, end)` -> POST /retrieve
- `listTree(prefix, depth)` -> GET /tree
- `setWeight(doc_id, multiplier)` -> POST /weight

Use an API gateway or direct URL. Include auth header. Provide JSON schemas matching request/response models.

---
## 9. Dynamic Weighting Flow
1. Base score from embeddings (dual or single).
2. Extension multiplier (from weights.yaml).
3. Path multiplier(s) (cumulative).
4. Model weight (static config + runtime overrides via `/weight`).
5. Adjusted score = base * extension_weight * model_weight (and any path multipliers folded into extension weight step).

Runtime `/weight` takes effect immediately on subsequent searches.

---
## 10. Updating / Rebuilding
| Action | Command |
|--------|---------|
| Pull repo updates | Re-run build script (it re-clones or fetches) |
| Change extension weights | Edit `config/weights.yaml` (no restart needed for runtime? restart or rebuild if cached) |
| Change embedding model | Delete / rename existing `knowledge_base/embeddings` and rebuild with new env vars |

---
## 11. Deployment Notes
- Containerize: build image with pre-built embeddings baked or mount a persistent volume.
- Health probe: `/health` (returns 200 once rag_service initialized) else 503.
- Concurrency: FastAPI async safe; weight updates are simple dict writes (low contention). For heavy load consider a lock if races appear.
- Persistence of runtime weights: currently in-memory; persist manually if needed (extend `set_weight`).

---
## 12. Troubleshooting
| Symptom | Cause | Fix |
|---------|-------|-----|
| 503 RAG service not initialized | `initialize_rag_service` not called / wrong paths | Call initializer with correct embeddings path |
| Empty search results | Embeddings not built / wrong path | Re-run build script, verify index directory |
| macOS OpenMP crash | MKL / libomp duplicate | `KMP_DUPLICATE_LIB_OK=TRUE` already set early |
| MCP tools not visible | Wrong path or PYTHONPATH | Use absolute paths in MCP config |

Enable debug logging:
```bash
export LOG_LEVEL=DEBUG
```
(add logic or run with `uvicorn --log-level debug`)

---
## 13. Roadmap (Optional)
- Persistence layer for runtime weights
- Additional retrieval filters (e.g. semantic rerank)
- Auth plugin / token validation

---
## 14. License
See parent repository license.

---
## 15. Minimal Verification Script
```bash
# After build & run
curl -H 'Authorization: Bearer TEST' 'http://localhost:8000/health'
```
Expect JSON with status + trace_id.

---
Happy searching.
