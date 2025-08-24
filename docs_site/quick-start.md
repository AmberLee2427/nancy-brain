# Quick Start

Get up and running with Nancy Brain in under 5 minutes.

## Installation

```bash
pip install nancy-brain
```

## Create Your First Knowledge Base

### 1. Initialize a Project

```bash
nancy-brain init my-knowledge-base
cd my-knowledge-base
```

This creates:
```
my-knowledge-base/
├── config/
│   ├── repositories.yml    # GitHub repos to index
│   ├── weights.yaml        # Search result weighting
│   └── articles.yml        # PDF articles (optional)
└── knowledge_base/         # Built embeddings will go here
```

### 2. Add Some Repositories

Edit `config/repositories.yml`:

```yaml
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
```

### 3. Build the Knowledge Base

```bash
nancy-brain build
```

This will:
- Clone the repositories
- Extract text from code and documentation
- Build AI embeddings for search
- Clean up temporary files

### 4. Search Your Knowledge Base

```bash
nancy-brain search "machine learning algorithms"
```

Expected output:
```
1. ml_frameworks/scikit-learn/doc/modules/linear_model.rst (score: 0.89)
   Linear models for regression and classification...

2. ml_frameworks/scikit-learn/sklearn/ensemble/__init__.py (score: 0.82)
   Ensemble methods for classification and regression...
```

### 5. Launch Web Interface

```bash
nancy-brain ui
```

Opens at `http://localhost:8501` with:
- **Search interface** - Test queries with live results
- **Repository management** - Add/remove repos visually
- **Build control** - Trigger rebuilds with options
- **System status** - Health checks and diagnostics

## What's Next?

- **[Configuration](configuration.md)** - Customize search weights and behavior
- **[VS Code Integration](integrations/vscode-mcp.md)** - Code alongside your knowledge base
- **[Research Workflow](tutorials/research-workflow.md)** - Academic use cases
- **[Python API](tutorials/python-api.md)** - Use Nancy Brain in your scripts

## Common Issues

### Build Failed with Git Errors
```bash
# Make sure Git is installed and accessible
git --version

# Check repository URLs are accessible
git ls-remote https://github.com/scikit-learn/scikit-learn
```

### No Search Results
```bash
# Verify embeddings were built
ls -la knowledge_base/embeddings/

# Check if any documents were indexed
nancy-brain search "test" --limit 10
```

### Permission Errors
```bash
# Make sure you have write permissions
chmod -R 755 my-knowledge-base/
```

## Advanced Setup

### With PDF Articles

Add research papers to your knowledge base:

```yaml
# config/articles.yml
research_papers:
  - name: "attention_is_all_you_need"
    url: "https://arxiv.org/pdf/1706.03762.pdf"
    description: "Transformer architecture paper"
```

Build with articles:
```bash
nancy-brain build --articles-config config/articles.yml
```

### Custom Search Weights

Boost certain file types in search results:

```yaml
# config/weights.yaml
extensions:
  .md: 1.5      # Boost markdown documentation
  .rst: 1.5     # Boost reStructuredText docs
  .py: 1.0      # Standard weight for Python code
  .txt: 0.8     # Lower weight for plain text

path_includes:
  "README": 2.0     # Boost README files heavily
  "tutorial": 1.5   # Boost tutorial content
  "example": 1.3    # Boost examples
```

### Development Environment

For contributing or advanced usage:

```bash
git clone https://github.com/AmberLee2427/nancy-brain.git
cd nancy-brain
pip install -e ".[dev,docs,pdf]"
```
