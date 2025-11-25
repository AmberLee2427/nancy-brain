# Nancy Brain TODO List

## 🚨 High Priority (Before PyPI Release)

### Code Quality & CI
- [x] **Fix black formatting issues** in CI
  - ✅ Updated black version to 25.1.0 for consistency
  - ✅ Reformatted all files with consistent version
  - ✅ Pre-commit hooks now pass locally and should pass in CI
  - ✅ Configured flake8 to use .flake8 config file for consistency
  - ✅ Applied formatting fixes to resolve VS Code file watching conflicts
  - ✅ Aligned CI workflow with local pre-commit configuration
  - ✅ Verified compatibility across Python 3.10, 3.11, 3.12
- [x] **Increase test coverage** to 60%+
  - ✅ Achieved 67% test coverage (exceeding target!)
  - ✅ Added comprehensive CLI tests 
  - ✅ Added admin UI utility tests
  - ✅ Added end-to-end integration tests
  - ✅ All 94 tests passing

### Package Polish
- [x] **Validate PyPI metadata** 
  - ✅ Built package successfully: `nancy_brain-0.1.0-py3-none-any.whl`
  - ✅ Installed from wheel with all dependencies resolved
  - ✅ CLI entry point `nancy-brain` works correctly
  - ✅ All commands functional (init, build, search, serve, ui, etc.)
  - ✅ Python imports work: core modules, CLI, admin UI
  - ✅ Dependencies properly resolved: FastAPI, Streamlit, txtai, PyTorch
  - ✅ Version detection works: `nancy-brain --version` → 0.1.0

## 📚 Documentation & Examples (Post-Release v0.1.x)

### Read the Docs Setup
- [x] **Set up MkDocs Material**
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
- [ ] **ML Engineer Setup Tutorial**
  - PyTorch/scikit-learn knowledge base
  - Code search and documentation
  - Team knowledge sharing
- [ ] **Python API Usage Examples**
  - Direct RAGService usage
  - Embedding and search examples
  - Custom integrations

## 🎨 Polish & UX (Future Versions)

### Web Interface Improvements
- [ ] **Enhanced Streamlit UI**
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
  - Graceful handling of missing dependencies
  - Clear validation errors for configuration files
  - Helpful hints for common user mistakes
- [ ] **Better CLI experience**
  - Progress bars for build operations
  - ✅ Colored output for better readability
  - Interactive configuration wizard
  - Auto-completion support
- [ ] **More build options**
  - ✅ `--dry-run` 
  - ✅ `--category` 
  - ✅ `--dirty`

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
  - Model comparison and benchmarking
  - ✅ Automatic model selection
- [ ] **Advanced PDF Processing**
  - Better table extraction
  - Image and figure processing
  - Citation link extraction
  - [ ] ADS API integration for article downloads
  - [ ] Implement DeepSeek OCR pipeline

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

## 📸 Content Creation (When Ready)

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

### v0.1.x (Current)
- [x] Basic package functionality
- [x] CLI interface
- [x] Web admin interface
- [x] PyPI publishing setup
- [x] CI/CD fixes (black formatting resolved)
- [x] Package validation and testing

### v0.2.x (Documentation Release)
- [x] Complete Read the Docs setup
- [ ] All integration examples
- [x] Improved test coverage
- [x] Better error handling

### v0.3.x (Polish Release)
- [ ] Enhanced UI/UX
- [ ] Performance improvements
- [ ] Advanced search features
- [ ] Production hardening

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
- [ ] Create GitHub issue templates
- [ ] Set up contributing guidelines
- [ ] Add code of conduct
- [ ] Create community discussion forum
- [ ] Reach out to potential users/contributors

## 🐞 Bug Squashing (User Feedback)

- [ ] **`explore_document_tree` returns only "unknown" entries.**
    - **Description:** The `explore_document_tree` tool is not working correctly. It should display the file and directory structure of the knowledge base, but instead it only shows "unknown" for all entries. This makes it impossible to browse the knowledge base.
- [ ] **`retrieve_document_passage` fails to find documents from search results.**
    - **Description:** The `retrieve_document_passage` tool consistently fails with a "Document not found" error when using a `doc_id` provided by the `search_knowledge_base` tool. This is a critical bug that breaks the core search and retrieval functionality. The `retrieve` function should be able to fetch the document content from the `txtai` index, as the server is not supposed to rely on the `raw` files.
- [ ] **Search relevance needs improvement.**
    - **Description:** The `search_knowledge_base` tool returns results with mixed relevance and low scores. While some results are good, others seem unrelated to the query. The search algorithm and/or the underlying embeddings should be investigated to improve the quality of the search results.
- [x] **`get_system_status` shows incorrect version information.**
    - ✅ **Description:** The `get_system_status` tool reports the version as `dev-0.1.0`, which is incorrect. The version information should be populated correctly from the build process to allow for proper version tracking.
- [x] **`get_system_status` shows "unknown" for build info.**
    - ✅ **Description:** The `get_system_status` tool reports "unknown" for `Build SHA` and `Built At`. This information should be populated during the build process to help with debugging and version tracking.
- [x] **`get_system_status` status message is not detailed enough.**
    - ✅ **Description:** The `get_system_status` tool reports a simple "ok" status. It would be more helpful if it provided more details about what checks were performed (e.g., "Registry: loaded, Store: loaded, Search: loaded").
- [x] **Investigate inconsistent version reporting.**
    - ✅ **Description:** The user reported seeing `dev-0.1.0` as the version, while the codebase is at `0.1.3`. This could be an environment issue, but it should be investigated to prevent confusion.
