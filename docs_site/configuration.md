# Configuration

Customize Nancy Brain's behavior through configuration files and environment variables.

## Configuration Files

Nancy Brain uses YAML configuration files to define repositories, search weights, and processing options.

### Repository Configuration (`config/repositories.yml`)

Define which GitHub repositories to index:

```yaml
# Group repositories by category
ml_frameworks:
  - name: "scikit-learn"
    url: "https://github.com/scikit-learn/scikit-learn"
    description: "Machine learning library for Python"
    is_notebook: false

  - name: "pytorch"  
    url: "https://github.com/pytorch/pytorch"
    description: "Deep learning framework"
    is_notebook: false

documentation:
  - name: "python-docs"
    url: "https://github.com/python/cpython"
    description: "Python source and documentation" 
    is_notebook: false

jupyter_examples:
  - name: "data-science-notebooks"
    url: "https://github.com/your-org/notebooks"
    description: "Data science tutorial notebooks"
    is_notebook: true  # Special handling for notebooks
```

**Fields:**
- `name`: Unique identifier within the category
- `url`: Git repository URL (HTTPS or SSH)
- `description`: Human-readable description
- `is_notebook`: Set to `true` for notebook-heavy repositories

**Categories** become path prefixes in search results (e.g., `ml_frameworks/scikit-learn/...`).

### Search Weights (`config/weights.yaml`)

Control which files get higher priority in search results:

```yaml
# Base multipliers by file extension
extensions:
  .md: 1.5        # Boost markdown documentation
  .rst: 1.5       # Boost reStructuredText docs  
  .txt: 1.2       # Boost plain text files
  .py: 1.0        # Standard weight for Python code
  .js: 0.9        # Slightly lower for JavaScript
  .json: 0.7      # Lower weight for config files
  .log: 0.3       # Very low for log files

# Additional multipliers for path patterns
path_includes:
  "README": 2.0       # Heavily boost README files
  "tutorial": 1.8     # Boost tutorial content
  "example": 1.5      # Boost example code
  "guide": 1.5        # Boost guide documentation
  "docs/": 1.3        # Boost files in docs directories
  "test": 0.8         # Lower weight for test files
  "__pycache__": 0.1  # Very low for cache files
```

**How it works:**
1. Base weight starts at 1.0
2. Extension multiplier is applied
3. Each matching path pattern multiplier is applied
4. Final weight = base × extension × path₁ × path₂ × ...

### PDF Articles (`config/articles.yml`)

Optionally include PDF research papers and documentation:

```yaml
research_papers:
  - name: "attention_is_all_you_need"
    url: "https://arxiv.org/pdf/1706.03762.pdf"
    description: "Transformer architecture paper (Vaswani et al.)"

  - name: "bert_paper"
    url: "https://arxiv.org/pdf/1810.04805.pdf" 
    description: "BERT: Pre-training of Deep Bidirectional Transformers"

documentation:
  - name: "python_tutorial"
    url: "https://docs.python.org/3/tutorial/tutorial.pdf"
    description: "Official Python Tutorial (PDF)"
```

**PDF Processing Requirements:**
- **Java** (for Apache Tika): `brew install openjdk`
- **Fallback libraries**: `pip install PyPDF2 pdfplumber pymupdf`

## Environment Variables

### Core Settings

| Variable | Default | Description |
|----------|---------|-------------|
| `USE_DUAL_EMBEDDING` | `true` | Enable separate code and text embedding models |
| `CODE_EMBEDDING_MODEL` | `microsoft/codebert-base` | Model for code embeddings |
| `KMP_DUPLICATE_LIB_OK` | `TRUE` | Fix OpenMP conflicts on macOS |

### PDF Processing

| Variable | Default | Description |
|----------|---------|-------------|
| `JAVA_HOME` | Auto-detected | Java installation path |
| `TIKA_SERVER_TIMEOUT` | `60` | Tika server timeout (seconds) |
| `SKIP_PDF_PROCESSING` | `false` | Skip PDF processing entirely |

### Development

| Variable | Default | Description |
|----------|---------|-------------|
| `NANCY_LOG_LEVEL` | `INFO` | Logging level (DEBUG, INFO, WARNING, ERROR) |
| `NANCY_CACHE_SIZE` | `1000` | Search result cache size |

## Runtime Configuration

### Dynamic Weights

Adjust document importance during runtime:

```bash
**Check knowledge base content:**
```bash
nancy-brain search "test" --limit 10
```
```

### Search Filters

Apply filters during search:

```bash
# Filter by category
nancy-brain search "machine learning" --category ml_frameworks

# Filter by file type
nancy-brain search "tutorial" --filetype .md

# Combine filters
nancy-brain search "example" --category documentation --filetype .py
```

## Advanced Configuration

### Custom Embedding Models

Override the default embedding models:

```bash
export USE_DUAL_EMBEDDING=true
export CODE_EMBEDDING_MODEL="microsoft/graphcodebert-base"
export TEXT_EMBEDDING_MODEL="sentence-transformers/all-MiniLM-L6-v2"
```

### Build Options

Customize the knowledge base build process:

```bash
# Build with custom paths
nancy-brain build \
  --config custom-repos.yml \
  --embeddings-path custom/embeddings \
  --force-update

# Build specific categories only
nancy-brain build --category ml_frameworks

# Keep raw files for debugging
nancy-brain build --dirty
```

### Performance Tuning

For large knowledge bases:

```yaml
# config/performance.yml
build:
  batch_size: 100        # Documents per batch
  max_workers: 4         # Parallel processing threads
  chunk_size: 512        # Text chunk size for embedding

search:
  cache_size: 2000       # Larger cache for frequent searches
  timeout: 30            # Search timeout seconds
  max_results: 100       # Maximum results to rank
```

## Configuration Examples

### Academic Research Setup

Perfect for research papers and related code:

```yaml
# config/repositories.yml
research_papers:
  - name: "paper-code"
    url: "https://github.com/author/paper-implementation"
    description: "Implementation code for our paper"
    is_notebook: true

reference_implementations:
  - name: "baseline-methods"
    url: "https://github.com/org/baseline-methods"
    description: "Baseline implementation for comparison"
    is_notebook: false
```

```yaml
# config/weights.yaml
extensions:
  .md: 2.0      # Heavy boost for documentation
  .ipynb: 1.8   # Boost notebooks
  .py: 1.5      # Boost Python code
  .pdf: 2.5     # Heavy boost for PDFs

path_includes:
  "paper": 3.0      # Heavily boost paper-related content
  "results": 2.0    # Boost results and figures
  "notebook": 1.8   # Boost notebook directories
```

### Software Development Setup

Focused on code documentation and examples:

```yaml
# config/repositories.yml
frameworks:
  - name: "main-framework"
    url: "https://github.com/your-org/framework"
    description: "Main framework repository"
    is_notebook: false

  - name: "examples"
    url: "https://github.com/your-org/examples"
    description: "Usage examples and tutorials"
    is_notebook: true

dependencies:
  - name: "core-library"
    url: "https://github.com/org/core-lib"
    description: "Core dependency library"
    is_notebook: false
```

```yaml
# config/weights.yaml
extensions:
  .py: 1.5      # Boost Python code
  .md: 1.8      # Boost documentation
  .yaml: 1.2    # Boost config files
  .json: 0.8    # Lower weight for data files

path_includes:
  "README": 3.0     # Critical for understanding
  "docs/": 2.0      # Documentation directory
  "examples/": 1.8  # Example code
  "api/": 1.5       # API documentation
  "test": 0.7       # Lower weight for tests
```

## Troubleshooting Configuration

### Validation

Check your configuration files:

```bash
# Validate repository config
nancy-brain validate-config config/repositories.yml

# Test search weights
nancy-brain test-weights config/weights.yaml

# Check PDF article URLs
nancy-brain validate-articles config/articles.yml
```

### Common Issues

**Repository clone failures:**
```bash
# Test repository access
git ls-remote https://github.com/org/repo.git

# Check SSH key setup for private repos
ssh -T git@github.com
```

**PDF download failures:**
```bash
# Test PDF URLs manually
curl -I https://arxiv.org/pdf/1706.03762.pdf

# Check Java installation for Tika
java -version
echo $JAVA_HOME
```

**Search weight not working:**
```bash
# Check weight calculation
nancy-brain explain-weights "path/to/document.md"

# Test specific patterns
nancy-brain test-pattern "README" --weights config/weights.yaml
```

## Next Steps

- **[Quick Start](quick-start.md)** - Build your first knowledge base
- **[VS Code Integration](integrations/vscode-mcp.md)** - Use in your development workflow  
- **[Python API](tutorials/python-api.md)** - Programmatic access to configuration
