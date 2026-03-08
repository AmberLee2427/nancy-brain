# Nancy Brain TODO List

## 🚨 High Priority (Before PyPI Release)

### Code Quality & CI
- ✅ **Fix black formatting issues** in CI
  - ✅ Updated black version to 25.1.0 for consistency
  - ✅ Reformatted all files with consistent version
  - ✅ Pre-commit hooks now pass locally and should pass in CI
  - ✅ Configured flake8 to use .flake8 config file for consistency
  - ✅ Applied formatting fixes to resolve VS Code file watching conflicts
  - ✅ Aligned CI workflow with local pre-commit configuration
  - ✅ Verified compatibility with Python 3.12
- ✅ **Increase test coverage** to 60%+
  - ✅ Achieved 67% test coverage (exceeding target!)
  - ✅ Added comprehensive CLI tests 
  - ✅ Added admin UI utility tests
  - ✅ Added end-to-end integration tests
  - ✅ All 94 tests passing

### Package Polish
- ✅ **Validate PyPI metadata** 
  - ✅ Built package successfully: `nancy_brain-0.1.0-py3-none-any.whl`
  - ✅ Installed from wheel with all dependencies resolved
  - ✅ CLI entry point `nancy-brain` works correctly
  - ✅ All commands functional (init, build, search, serve, ui, etc.)
  - ✅ Python imports work: core modules, CLI, admin UI
  - ✅ Dependencies properly resolved: FastAPI, Streamlit, txtai, PyTorch
  - ✅ Version detection works: `nancy-brain --version` → 0.1.0

## 📚 Documentation & Examples (Post-Release v0.1.x)

### Read the Docs Setup
- ✅ **Set up MkDocs Material**
  - ✅ Create `docs_site/` directory structure
  - ✅ Configure `mkdocs.yml` with material theme
  - ✅ Set up Read the Docs project
  - ✅ Add GitHub Actions for auto-deploy

### Integration Examples (with Screenshots Later)
- [-] **VS Code + MCP Integration**
  - ✅ Step-by-step setup guide
  - ✅ Sample workspace configuration
  - Demo with real repository
  - [x] **Gemini Code Assist + VSCode + MCP Integration**
    - ✅ User test 
  - [ ] **Update for native Chat integreation**
- [ ] **Cursor + MCP Integration**
- [ ] **Claude Desktop Integration**
  - Configuration file example
  - Usage demonstration
  - Troubleshooting common issues
- [ ] **Custom GPT (OpenAI) Integration**
  - Action schema definitions
  - API endpoint mapping
  - Example GPT configuration
- [ ] **Slack Bot Integration**
  - Bot setup and token configuration
  - Event subscription setup
  - Usage examples

### Tutorial Content
- [x] **Researcher Workflow Tutorial**
  - ✅ Academic paper + GitHub repo workflow
  - ✅ PDF article management
  - ✅ Search and retrieval examples
~~- [ ] **ML Engineer Setup Tutorial**~~
  ~~- PyTorch/scikit-learn knowledge base~~
  ~~- Code search and documentation~~
  ~~- Team knowledge sharing~~
- [ ] **Python API Usage Examples**
  - Direct RAGService usage
  - Embedding and search examples
  - Custom integrations

## 🎨 Polish & UX (Future Versions)

### Web Interface Improvements
- ✅ **Enhanced Streamlit UI**
  - ✅ Better error handling and feedback
  - ✅ Progress bars for long operations
  - ✅ Export/import configurations
  - ✅ Search result highlighting
  - ✅ Use reweighting processes in UI search so we can test out config options
  - ✅ Add thumbs up thumbs down button and link it to the `model_weights.yml` to boost/suppress good/bad results
  - ✅ Mock testing

### CLI Enhancements
- [ ] **Improved CLI error handling**
  - Better error messages with actionable suggestions
  - Clear validation errors for configuration files
- [ ] **Better CLI experience**
  -  [ ]Progress bars for build operations
  - ✅ Colored output for better readability
  - [ ] Interactive configuration wizard
  - [ ] Auto-completion support
- ✅ **More build options**
  - ✅ `--dry-run` 
  - ✅ `--category` 
  - ✅ `--dirty`
  - ✅ `--repo` filter — build a single named repo; enables per-repo parallelism across cluster nodes

### Summary Generation
- ✅ **Small-file skip**: skip summarization for files below a stripped-char threshold (≈200 chars); use content size only — do NOT use filename heuristics (`__init__.py` can contain critical code)
- ✅ **Data-file skip**: skip binary/data files by extension (`.fits`, `.npy`, `.pkl`, `.dat`, `.csv`, `.parquet`, images, compiled objects, etc.)
- ✅ **Configurable local summary model**: honour `NB_SUMMARY_MODEL` env var (default `Qwen/Qwen2.5-Coder-0.5B-Instruct`); GPU users can point this at a larger model (e.g. `Qwen2.5-Coder-7B`) for better quality — the code already auto-detects GPU via `device_map="auto"`
- [ ] **Repo-level summary mode**: one LLM call per repo (README + dir listing + top N files) as a fast-build alternative to per-file calls
- ✅ `nancy-brain import-env -f environment.yml` — generate `repositories.yml` entries from a conda env file; category = env name
- ✅ **Version/ref pinning** in `repositories.yml` — optional `ref:` field per repo for reproducible KB builds

### Auth
- [ ] create an admin login account
- [ ] create test keys and add as env variable and github secrets (for CI)
- [ ] add a "keys" page to the admin interface

### Advanced Features
- [ ] **Enhanced Search**
  - [ ] **Refactor search to use txtai's SQL-like queries**
  - Semantic reranking
  - Search result caching
  - Custom scoring algorithms
  - Search history and favorites
- [ ] **Multi-model Support**
  - ✅ Support for different embedding models
  - [ ] Model comparison and benchmarking
  - ✅ Automatic model selection
- [ ] **PDF Processing: Replace Tika with OCR pipeline**
  - [ ] Remove Tika-based pipeline (`pdf_utils.py`, `manage_pdf_articles.py`) — it's unreliable and being replaced
  - [ ] **DeepSeek OCR** as primary backend (GPU, ~7B VLM): PDF pages → images → structured Markdown
  - [ ] **Nougat** (`nougat-ocr`) as CPU fallback (~250M): same image→Markdown pipeline, no GPU required
  - [ ] Install extras: `pip install nancy-brain[ocr]` (nougat + pymupdf) and `[ocr-gpu]` (pymupdf; needs CUDA torch)
  - [ ] Auto-detect backend at build time: CUDA + DeepSeek available → use it; else nougat; else skip with warning
  - [ ] OCR output is Markdown → feeds into `MarkdownHeadingChunker` → same embedding space as everything else
  - [ ] Cache OCR Markdown output per-PDF (content-hash) so rebuilds don't re-process unchanged articles
  - [ ] Citation link extraction (post-OCR, future)
- ✅ **Article source import**
  - ✅ `nancy-brain import-bibtex -f references.bib` → populates `articles.yml`
  - ✅ `nancy-brain import-ads --library "My Library"` → populates `articles.yml` via ADS API
- [ ] **MCP Re-hosted Tools**
  - memory mcp
  - wikipedia mcp
  - arxiv mcp
  - github mcp
  

## 🔧 Technical Debt & Maintenance

### Code Improvements
- [ ] **Refactor service initialization**
  - Cleaner dependency injection
  - Better error handling
  - Configuration validation
- [ ] **Fix retrieve to use indexed content instead of raw files**
  - `retrieve` should serve passages from the embeddings/indexed store (what search returns), not depend on raw files existing on disk
  - Ensure GitHub URLs and line ranges are derived from indexed metadata
- [ ] **Improve logging**
  - Structured logging with levels
  - Better error messages
  - Debug mode support
- [ ] **Commit minimal KB artifacts for slack-bot tests**
  - Include enough embeddings/configs in `ref/nancy-brain/knowledge_base` so slack-bot MCP integration tests run without manual KB builds
  - include them in the manifest and fetch them from package files with `nancy-brain get-test-KB`, or somehting like that.
  The goal is a minimal running KB that can be built from a PyPI install of nancy-brain
- [ ] **Performance optimizations**
  - Lazy loading of models
  - Caching improvements
  - Memory usage optimization

### Infrastructure
- [ ] **Monitoring & Observability**
  - ✅ Health check endpoints
  - Metrics collection
  - Error tracking
- [ ] **Security**
  - Input validation
  - ✅ Rate limiting
  - ✅ Authentication improvements

### Hosting
- [ ] Host a remote MCP server
- [ ] Actions
- [ ] Custom GPT

### Chunking
- [x] Delegate to a subpackage (`chunky`) — v2.1.0 with forward-merge and tree-sitter `max_chars` fix
- [ ] **Tree-sitter gap-filling** (Option A): emit non-function spans so 100% of C/C++/Bash/HTML files are indexed (see `chunky/docs/design/TREESITTER_COVERAGE_BUG.md`)
- [ ] Broader per-language tree-sitter queries (Option B, tracked in `chunky/TODO.md`)
- [ ] Notebook chunking review
- [ ] Visual inspection checks once OCR pipeline produces Markdown output

## 📸 Content Creation (lowest priority)

### Screenshots & Media
- [ ] **Web UI Screenshots**
  - Search interface in action
  - Repository management screens
  - Build process visualization
- [ ] **Integration Screenshots**
  - VS Code with MCP tools active
  - Claude Desktop with nancy-brain
  - Slack bot conversations

## 🚀 Release Milestones

### v0.1.x 
- [x] Basic package functionality
- [x] CLI interface
- [x] Web admin interface
- [x] PyPI publishing setup
- [x] CI/CD fixes (black formatting resolved)
- [x] Package validation and testing

### v0.2.x (Documentation Release)
- [x] Complete Read the Docs setup
- [ ] ~~All integration examples~~
- [x] Improved test coverage
- [x] Better error handling

### v0.3.x (Polish Release)
- [x] Enhanced UI/UX
- [x] Performance improvements
- [x] Advanced search features

### v0.4.x (Containerize - complete)
- [x] MCP Server Dockerization (in ref/nancy-brain/)
 * [x] Create Dockerfile and build workflow for embeddings/model readiness
 * [x] Add /rebuild API endpoint for triggering updates
 * [x] Implement simple API key auth middleware
- [x] Slack Bot Docker Setup (root directory)
 * [x] Dockerfile for the bot service
 * [x] docker-compose.yml connecting bot → MCP server
 * [x] Environment variable management
- [x] API Key Configuration
 * [x] Add MCP_API_KEY to both services
 * [x] Add API-key issuance endpoints/flows
 * [x] Update MCPRAGAdapter to send auth headers

### v0.5.0 (Beta testing for user readiness - current)
- [ ] Working NancyGPT
- [ ] Adoption instruction for NancyBrain (with actual, live MCP server address) and link to the NancyGPT in the NancyBot Slack home page. 
- [ ] Debug issues Nancy is experiencing with the NancyBrain MCP.
  - Retrieve
  - Tree
  - Search
- [ ] Debug any issues NancyGPT is having with NancyBrain Actions
- [ ] Finish summary generation for remaining files (~30K files on Unity; use existing cache)
- [ ] `--repo` CLI option for parallel per-repo builds across cluster nodes
- [ ] Small-file and data-file summary skipping to reduce compute waste
- [ ] Pre-process ~30 articles with DeepSeek OCR on GPU node for conference demo

### v1.0.x (Stable Release)
- [ ] Full feature completeness
- [ ] Comprehensive testing
- [ ] Production deployments
- [ ] Community adoption

---

## ⚡ Quick Wins (Can Do Anytime)
- [x] Add more file type support (.txt, .rst, .tex)
- [x] Improve CLI help text and examples
- [x] Add configuration file validation
- [ ] Create sample configuration templates
- [ ] Add health check for dependencies
- [ ] Add category back as a build option

## 🤝 Community & Adoption
- [ ] Set up contributing guidelines
- [ ] Add code of conduct

## 🐞 Bug Squashing (User Feedback)
- [-] **Nancy-Brain UI does update summaries**
   - **Description:** exact circumstsances for failure are unknown, but the bug was noted after migrating to docker builds and local model summaries. We suspect a permision issue with the subprocess.
   - I think this is fine now. We are building local summaries on a faster machine and transfering them for the initial build.
- [ ] **`explore_document_tree` returns only "unknown" entries.**
    - **Description:** The `explore_document_tree` tool is not working correctly. It should display the file and directory structure of the knowledge base, but instead it only shows "unknown" for all entries. This makes it impossible to browse the knowledge base.
- [ ] **`retrieve_document_passage` fails to find documents from search results.**
    - **Description:** The `retrieve_document_passage` tool consistently fails with a "Document not found" error when using a `doc_id` provided by the `search_knowledge_base` tool. This is a critical bug that breaks the core search and retrieval functionality. The `retrieve` function should be able to fetch the document content from the `txtai` index, as the server is not supposed to rely on the `raw` files.
- ✅ **Search relevance needs improvement.**
    - **Description:** The `search_knowledge_base` tool returns results with mixed relevance and low scores. While some results are good, others seem unrelated to the query. The search algorithm and/or the underlying embeddings should be investigated to improve the quality of the search results.
- ✅ **`get_system_status` shows incorrect version information.**
    - ✅ **Description:** The `get_system_status` tool reports the version as `dev-0.1.0`, which is incorrect. The version information should be populated correctly from the build process to allow for proper version tracking.
- [x] **`get_system_status` shows "unknown" for build info.**
    - ✅ **Description:** The `get_system_status` tool reports "unknown" for `Build SHA` and `Built At`. This information should be populated during the build process to help with debugging and version tracking.
- [x] **`get_system_status` status message is not detailed enough.**
    - ✅ **Description:** The `get_system_status` tool reports a simple "ok" status. It would be more helpful if it provided more details about what checks were performed (e.g., "Registry: loaded, Store: loaded, Search: loaded").
- [x] **Investigate inconsistent version reporting.**
    - ✅ **Description:** The user reported seeing `dev-0.1.0` as the version, while the codebase is at `0.1.3`. This could be an environment issue, but it should be investigated to prevent confusion.
