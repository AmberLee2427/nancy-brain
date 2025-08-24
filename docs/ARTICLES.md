# Journal Article Management

This directory contains tools for managing journal articles (PDFs) in Nancy's knowledge base. There are now **two approaches** for handling PDF articles:

## 🆕 **Integrated Pipeline Approach** (Recommended)

The main knowledge base build pipeline now supports downloading PDFs from URLs and integrating them into the embeddings, just like repositories.

### Setup

1. **Configure PDF articles** in `config/articles.yml`:
   ```yaml
   journal_articles:
     - name: "Paczynski_1986_ApJ_304_1"
       url: "https://ui.adsabs.harvard.edu/link_gateway/1986ApJ...304....1P/PUB_PDF"
       description: "Paczynski (1986) - Gravitational microlensing by the galactic halo"
   
   microlensing_reviews:
     - name: "Mao_2012_RAA_12_947"
       url: "https://ui.adsabs.harvard.edu/link_gateway/2012RAA....12..947M/PUB_PDF"
       description: "Mao (2012) - Introduction to gravitational microlensing"
   ```

2. **Build the complete knowledge base** (repos + PDFs):
   ```bash
   # RECOMMENDED: Use the new build script with proper Java environment
   ./build_with_java.sh
   
   # OR manually set up environment and run:
   export JAVA_HOME="/opt/homebrew/opt/openjdk"
   export PATH="/opt/homebrew/opt/openjdk/bin:$PATH"
   export KMP_DUPLICATE_LIB_OK=TRUE
   conda activate roman-slack-bot
   
   # Build everything (downloads repos and PDFs, creates embeddings, cleans up)
   python scripts/build_knowledge_base.py --config config/repositories.yml --articles-config config/articles.yml
   
   # Build only PDF articles
   python scripts/build_knowledge_base.py --category journal_articles
   
   # Keep raw files for inspection
   python scripts/build_knowledge_base.py --dirty
   ```

### Features

- ✅ **URL-based PDF downloads** - just like repositories, but for PDFs
- ✅ **Automatic cleanup** - downloads, processes, and cleans up PDFs
- ✅ **Integrated embeddings** - PDFs included in the same search index as code
- ✅ **Metadata preservation** - title, description, and URL included in search results
- ✅ **Categorized organization** - separate categories like `journal_articles`, `reviews`, etc.
- ✅ **Robust PDF processing** - Multiple fallback methods when Tika fails
- ✅ **Java environment auto-setup** - Automated via `build_with_java.sh`
- ✅ **Troubleshooting tools** - Diagnostic notebook for debugging issues

## 📄 **Standalone PDF Manager**

For manual PDF management, there's also a dedicated tool:

```bash
# Download PDFs by category
python scripts/manage_pdf_articles.py --category journal_articles

# List all configured PDFs
python scripts/manage_pdf_articles.py --list

# Download all PDFs
python scripts/manage_pdf_articles.py

# Clean up orphaned PDFs
python scripts/manage_pdf_articles.py --clean
```

## 🔧 **Legacy Individual Article Manager**

The original `manage_articles.py` script for manually adding individual PDFs:

```bash
# Add a single PDF
python scripts/manage_articles.py add /path/to/paper.pdf

# List existing articles  
python scripts/manage_articles.py list
```

## 🏗️ **Architecture**

### Integrated Pipeline Flow:
1. **Download repos** → Clone git repositories  
2. **Download PDFs** → Fetch PDFs from configured URLs
3. **Extract text** → Use txtai Textractor + Apache Tika for PDF text extraction
4. **Build embeddings** → Index both code and PDF content together
5. **Cleanup** → Remove raw files, keep only embeddings

### File Organization:
```
knowledge_base/
├── raw/                           # Temporary downloads (cleaned up)
│   ├── journal_articles/          # PDF downloads by category
│   │   ├── Paczynski_1986.pdf
│   │   └── Mao_2012.pdf  
│   └── microlensing_tools/        # Git repo clones
│       ├── pyLIMA/
│       └── MulensModel/
└── embeddings/                    # Persistent search index
    └── index/                     # txtai FAISS index
```

## 🔧 **Setup Requirements**

```bash
# Ensure dependencies
conda activate roman-slack-bot
pip install "txtai[pipeline]"

# macOS users: handle OpenMP conflicts
export KMP_DUPLICATE_LIB_OK=TRUE

# CRITICAL: Java required for PDF processing
# Install Java if not already installed:
brew install openjdk  # macOS
# sudo apt-get install openjdk-11-jdk  # Ubuntu/Debian

# Set up Java environment (REQUIRED for Tika PDF processing)
export JAVA_HOME="/opt/homebrew/opt/openjdk"
export PATH="/opt/homebrew/opt/openjdk/bin:$PATH"

# Verify Java is working:
java -version
```

## ⚠️ **Known Issues & Solutions**

1. **~~Tika Server Issues~~**: ✅ **FIXED** - Previous startup problems with Apache Tika server for PDF processing have been resolved
   - **Solution**: Use `./build_with_java.sh` which properly sets up Java environment
   - **Root Cause**: Java PATH configuration issues have been addressed

2. **PDF URL Reliability**: Some publisher PDFs require authentication or have changing URLs
   - Use stable URLs like arXiv: `https://arxiv.org/pdf/1234.5678.pdf`
   - ADS gateway URLs may have redirect limits or access restrictions

3. **Java Environment**: If you encounter "Unable to locate a Java Runtime" errors
   - Install Java: `brew install openjdk` (macOS) 
   - Set environment: `export JAVA_HOME="/opt/homebrew/opt/openjdk"`
   - Use the provided `build_with_java.sh` script for automatic setup

## 🎯 **Usage Patterns**

### For Development/Testing:
```bash
# RECOMMENDED: Use the new build script with Java environment setup
./build_with_java.sh

# Test the pipeline with dry run
python scripts/build_knowledge_base.py --dry-run

# Download specific category only  
python scripts/build_knowledge_base.py --category roman_mission

# Keep files for debugging
python scripts/build_knowledge_base.py --dirty

# If you need to troubleshoot, use the diagnostic notebook:
jupyter notebook knowledge_base_troubleshooting.ipynb
```

### For Production:
```bash
# RECOMMENDED: Full rebuild with Java environment setup
./build_with_java.sh

# Full rebuild (everything) - manual approach
export JAVA_HOME="/opt/homebrew/opt/openjdk"
export PATH="/opt/homebrew/opt/openjdk/bin:$PATH"
python scripts/build_knowledge_base.py --force-update

# Regular update (only new content)
python scripts/build_knowledge_base.py
```

### For PDF Management:
```bash
# Quick PDF status check
python scripts/manage_pdf_articles.py --list

# Add individual PDF
python scripts/manage_articles.py add /path/to/new_paper.pdf

# Troubleshoot any issues
jupyter notebook docs/knowledge_base_troubleshooting.ipynb
```
