# Knowledge Base Management Scripts

This directory contains scripts for managing Nancy's comprehensive knowledge base, including both GitHub repositories and PDF articles.

## 🚀 **Quick Start**

### **Complete Knowledge Base Build** (Recommended)
```bash
export KMP_DUPLICATE_LIB_OK=TRUE  # macOS users
conda activate roman-slack-bot

# Build everything: repos + PDFs → embeddings
python scripts/build_knowledge_base.py

# Build specific category only
python scripts/build_knowledge_base.py --category microlensing_tools

# Dry run to see what would happen
python scripts/build_knowledge_base.py --dry-run
```

### **Repository Management**
```bash
# List all configured repositories
python scripts/manage_repositories.py --list

# Clone/update all repositories
python scripts/manage_repositories.py

# Update specific category
python scripts/manage_repositories.py --category jupyter_notebooks
```

### **PDF Article Management**
```bash
# Download and index PDFs from config/articles.yml
python scripts/build_knowledge_base.py --config config/repositories.yml --articles-config config/articles.yml

# Add individual PDFs manually
python scripts/manage_articles.py add /path/to/paper.pdf
```

## 📋 **Available Scripts**

| Script | Purpose | Key Features |
|--------|---------|--------------|
| `build_knowledge_base.py` | **Main pipeline** | Downloads repos + PDFs, builds embeddings, cleanup |
| `manage_repositories.py` | Git repository management | Clone, update, list repos from config |
| `manage_articles.py` | Individual PDF management | Add single PDFs manually |

## ⚙️ **Configuration Files**

### **`config/repositories.yml`** - Git Repositories
```yaml
microlensing_tools:
  - name: pyLIMA
    url: https://github.com/ebachelet/pyLIMA.git
    description: "pyLIMA microlensing modeling"

jupyter_notebooks:
  - name: roman_notebooks
    url: https://github.com/spacetelescope/roman_notebooks.git
    description: "Roman mission notebooks"
```

### **`config/articles.yml`** - PDF Articles  
```yaml
journal_articles:
  - name: "Paczynski_1986_ApJ_304_1"
    url: "https://ui.adsabs.harvard.edu/link_gateway/1986ApJ...304....1P/PUB_PDF"
    description: "Paczynski (1986) - Gravitational microlensing by the galactic halo"

roman_mission:
  - name: "Spergel_2015_arXiv_1503.03757"
    url: "https://arxiv.org/pdf/1503.03757.pdf"
    description: "Spergel et al. (2015) - WFIRST-AFTA 2015 Report"
```

## 📂 **Repository Categories**

- **`microlensing_tools`**: Core analysis libraries (pyLIMA, MulensModel, VBMicrolensing, etc.)
- **`general_tools`**: Astronomy and Roman related tools (emcee, dynesty, romanisim, etc.)
- **`jupyter_notebooks`**: Tutorial notebooks and examples  
- **`web_resources`**: Documentation and web content
- **`microlens_submit`**: Data challenge submission tools

## 📄 **PDF Article Categories**

- **`journal_articles`**: Key microlensing papers (Paczynski, Mao, Gould, etc.)
- **`microlensing_reviews`**: Review articles and introductions
- **`roman_mission`**: Roman Space Telescope mission papers
- **`data_challenge`**: Data challenge documentation

## 🏗️ **How The Pipeline Works**

### **Integrated Build Process:**
1. **Download repos** → Clone/update git repositories from `repositories.yml`
2. **Download PDFs** → Fetch PDF articles from URLs in `articles.yml`  
3. **OCR to Markdown** → Render PDF pages with PyMuPDF and run DeepSeek OCR (with cache reuse)
4. **Build embeddings** → Create unified search index with both code and papers
5. **Cleanup** → Remove raw files, keep only the embeddings

### **File Organization:**
```
knowledge_base/
├── raw/                    # Temporary downloads (auto-cleaned)
│   ├── microlensing_tools/ # Git repositories
│   │   ├── pyLIMA/
│   │   └── MulensModel/
│   └── journal_articles/   # Downloaded PDFs  
│       ├── Paczynski_1986.pdf
│       └── Mao_2012.pdf
└── embeddings/             # Persistent search index
    ├── index/              # General embeddings (used by Nancy)
    │   ├── config.json
    │   ├── documents
    │   └── embeddings
    └── code_index/         # Code-specific embeddings (dual embedding)
        ├── config.json
        ├── documents
        └── embeddings
```

## 🔧 **Advanced Usage**

### **Development & Testing**
```bash
# See what would be built without actually doing it
python scripts/build_knowledge_base.py --dry-run

# Build but keep raw files for inspection
python scripts/build_knowledge_base.py --dirty

# Force re-download everything
python scripts/build_knowledge_base.py --force-update

# Process only specific categories
python scripts/build_knowledge_base.py --category journal_articles
```

### **Maintenance Operations**
```bash
# Clean up orphaned repositories (dry run first!)
python scripts/manage_repositories.py --clean --dry-run
python scripts/manage_repositories.py --clean

# Manual article management
python scripts/manage_articles.py list
python scripts/manage_articles.py add /path/to/new_paper.pdf
python scripts/manage_articles.py remove "journal_articles/article_name"
```

## 📦 **Dependencies**

```bash
# Core requirements (in the nancy-brain env)
pip install "nancy-brain[ocr-gpu]"  # DeepSeek OCR path
# or CPU-oriented extras for the future Nougat fallback
pip install "nancy-brain[ocr]"
pip install requests          # PDF downloads  
pip install pyyaml           # Config files
```

## 🐛 **Troubleshooting**

### **macOS OpenMP Issues**
```bash
export KMP_DUPLICATE_LIB_OK=TRUE
conda activate roman-slack-bot
```

### **OCR Backend Issues**
If PDF processing fails because OCR is unavailable:
```bash
# Re-run and keep the raw PDFs for inspection
python scripts/build_knowledge_base.py --category journal_articles --dirty
```

### **PDF Download Issues**
- Some publisher PDFs require authentication
- Use stable URLs (arXiv works reliably: `https://arxiv.org/pdf/####.####.pdf`)
- OCR Markdown is cached under `knowledge_base/cache/pdf_ocr`; deleting a hash entry forces re-processing

## 🎯 **Integration with Nancy**

The knowledge base scripts feed directly into Nancy's RAG system:

1. **Build Process** → Creates `knowledge_base/embeddings/index/` and `knowledge_base/embeddings/code_index/`
2. **Nancy's RAG Service** → Loads embeddings for semantic search
   ```python
   # Configure RAG service to use the built embeddings
   rag = RAGService(
       config_path=Path('config/repositories.yml'),
       embeddings_path=Path('knowledge_base/embeddings/index'),  # Point to index subfolder
       weights_path=Path('config/weights.yaml'),
       use_dual_embedding=True  # Enables code_index usage
   )
   ```
3. **User Queries** → Search across both code repositories and research papers
4. **Results** → Nancy can cite specific papers, code files, or notebooks

This gives Nancy comprehensive knowledge spanning both the **implementation** (code) and **theory** (papers) of microlensing!
2. **Updates**: For existing repositories, it runs `git fetch` and `git pull` to get the latest changes3 **Organization**: Repositories are organized by category in `knowledge_base/raw/`
4**Configuration**: Uses YAML configuration for easy management

## Benefits of This Approach

- **Easy Refresh**: Just run the script to get the latest versions of all repositories
- **No Manual Work**: No need to manually clone or update repositories
- **Version Control**: Git handles all the version management
- **Flexible**: Easy to add/remove repositories by editing the config file
- **Clean**: Can remove repositories that are no longer needed

## Example Workflow

```bash
# 1. Check what repositories are configured
python scripts/manage_repositories.py --list

# 2. Refresh all repositories to latest versions
python scripts/manage_repositories.py

# 3. Check for any orphaned repositories
python scripts/manage_repositories.py --clean --dry-run

# 4 youre happy with the changes, actually clean up
python scripts/manage_repositories.py --clean
```

This approach is much better than manually cloning repositories because:
- You can easily refresh everything with one command
- The configuration is version controlled
- You can see exactly what repositories are being tracked
- Its easy to add new repositories or remove old ones 
