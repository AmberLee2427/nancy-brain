# Troubleshooting Guide

This page contains solutions to common issues when working with Nancy Brain.

## Installation Issues

### Package Installation Fails

If you encounter issues installing Nancy Brain:

```bash
# Try upgrading pip first
pip install --upgrade pip

# Install with verbose output to see what's happening
pip install -v nancy-brain
```

### ERROR: Could not install packages due to an OSError: [Errno 28] No space left on device

You may get this error when installing nancy-brain, despite have plenty of storage space on your machine.
This can be an issues caused by yoou `/tmp/` or `~/.cache/` directories become full before the package finishes installing dependencies.

**Solution:** You can temporarily resize your `/tmp/` directory using:

```bash
sudo mount -o remount,size=8G /tmp
```

This change will last until you reboot. For a permanent change, you would need to edit your `/etc/fstab` file.

**Solution:** Work arounds, not requiring `su` permissions, are to install using:

```bash
pip install --no-cache-dir nancy-brain
```

or pre-installing larger dependencies:

```bash
pip install torch>=1.12.1
pip install faiss-cpu>=1.7.1.post2
pip install nvidia-cublas-cu12 nvidia-cudnn-cu12 nvidia-cusparse-cu12 nvidia-cusparselt-cu12
```

### Missing Dependencies

If you get import errors:

```bash
# Install with all optional dependencies
pip install "nancy-brain[all]"
```

### OpenMP/MKL Library Conflicts (macOS)

**This is extremely common on macOS!** If you see errors like:
- `OMP: Error #15: Initializing libiomp5.dylib, but found libomp.dylib already initialized`
- `Fatal Python error: Aborted`
- Process crashes when importing ML libraries

**Solution:**
```bash
# ALWAYS set this before running Nancy Brain on macOS
export KMP_DUPLICATE_LIB_OK=TRUE

# Add to your shell profile to make it permanent
echo 'export KMP_DUPLICATE_LIB_OK=TRUE' >> ~/.zshrc
source ~/.zshrc
```

This is caused by conda environments having multiple OpenMP libraries that conflict.

## PDF Processing Issues

### Tika Server Won't Start

**This is the #1 PDF processing issue!** If you see:
- `Failed to see startup log message`
- `TikaServerEndpoint not available`
- `java.net.ConnectException: Connection refused`

**Root Cause:** Java environment not properly configured.

**Solution:**
```bash
# 1. Install Java if not already installed
brew install openjdk  # macOS
# sudo apt-get install openjdk-11-jdk  # Ubuntu

# 2. Set up Java environment (CRITICAL!)
export JAVA_HOME="/opt/homebrew/opt/openjdk"
export PATH="/opt/homebrew/opt/openjdk/bin:$PATH"

# 3. Verify Java is working
java -version

# 4. Use the provided build script that sets up environment
./build_with_java.sh
```

### Tika Server Timeouts

If Tika starts but hangs during PDF processing:

```bash
# Set longer timeouts
export TIKA_SERVER_TIMEOUT="120"
export TIKA_CLIENT_TIMEOUT="120" 
export TIKA_STARTUP_TIMEOUT="180"

# Disable OCR (can be slow)
export TIKA_OCR_STRATEGY="no_ocr"

# Give Java more memory
export JAVA_OPTS="-Xmx2g -XX:+UseG1GC"
```

### PDF Download Failures

**Common with academic paper URLs!** If you see:
- `Exceeded 30 redirects`
- `403 Forbidden`
- `Connection timeout`

**Solutions:**
1. **Use direct PDF URLs when possible:**
   ```yaml
   # Good: Direct arXiv links
   - url: "https://arxiv.org/pdf/1234.5678.pdf"
   
   # Problematic: ADS gateway links (may redirect too much)
   - url: "https://ui.adsabs.harvard.edu/link_gateway/..."
   ```

2. **Download PDFs manually and use local files:**
   ```bash
   # Add local PDFs instead of URLs
   nancy-brain add-article /path/to/downloaded_paper.pdf
   ```

3. **Skip problematic PDFs temporarily:**
   ```yaml
   # Comment out failing downloads in config/articles.yml
   # journal_articles:
   #   - name: "problematic_paper"
   #     url: "https://problematic-url.com/paper.pdf"
   ```

### PDF Processing Fallbacks

If Tika fails completely, Nancy Brain has fallback methods:

```bash
# Install alternative PDF libraries
pip install PyPDF2 pdfplumber pymupdf

# Build without Tika (uses fallbacks automatically)
export SKIP_TIKA=true
nancy-brain build
```

### Java Environment Issues

**"Unable to locate a Java Runtime"**

```bash
# Check if Java is installed
which java
java -version

# If not found, install Java
brew install openjdk  # macOS
sudo apt-get install default-jdk  # Ubuntu

# Set JAVA_HOME (crucial for Tika)
export JAVA_HOME="/opt/homebrew/opt/openjdk"  # macOS
export JAVA_HOME="/usr/lib/jvm/default-java"  # Ubuntu

# Add to PATH
export PATH="$JAVA_HOME/bin:$PATH"
```

### Connection Problems

If Claude Desktop can't connect to Nancy Brain:

1. **Check the server is running:**
   ```bash
   python -m nancy_brain.connectors.mcp_server
   ```

2. **Verify configuration:**
   - Check your Claude Desktop config file
   - Ensure the path to `run_mcp_server.py` is correct
   - Verify the knowledge base path exists

3. **Check logs:**
   - Look for error messages in terminal
   - Check Claude Desktop developer console

### Performance Issues

If searches are slow or hanging:

1. **Check knowledge base size:**
   ```bash
   nancy-brain explore --max-depth 2
   ```

2. **Rebuild if needed:**
   ```bash
   nancy-brain build
   ```

## CLI Issues

### Command Not Found

If `nancy-brain` command isn't available:

```bash
# Make sure you installed the package
pip install nancy-brain

# Or install in development mode
pip install -e .
```

### Search Returns No Results

If searches return empty results:

1. **Check knowledge base exists:**
   ```bash
   ls -la knowledge_base/embeddings/
   ```

2. **Rebuild the knowledge base:**
   ```bash
   nancy-brain build
   ```

3. **Try different search terms:**
   ```bash
   nancy-brain search "your query" --limit 10
   ```

## Knowledge Base Build Issues

### Build Script Crashes Immediately

**Check these first:**
```bash
# 1. Set the magic macOS fix
export KMP_DUPLICATE_LIB_OK=TRUE

# 2. Make sure conda environment is activated
conda activate roman-slack-bot  # or your environment name

# 3. Check Java setup
java -version
echo $JAVA_HOME

# 4. Use the provided wrapper script
./build_with_java.sh
```

### "No module named txtai" or Similar Import Errors

```bash
# Make sure you're in the right environment
conda activate roman-slack-bot

# Install missing dependencies
pip install "txtai[pipeline]" requests pyyaml

# Check what's installed
pip list | grep -E "(txtai|tika|requests|yaml)"
```

### Build Hangs on PDF Processing

**Usually Tika server issues:**
```bash
# Kill any hanging Tika processes
pkill -f "tika-server"

# Set up environment properly and try again
export JAVA_HOME="/opt/homebrew/opt/openjdk"
export PATH="/opt/homebrew/opt/openjdk/bin:$PATH"
export KMP_DUPLICATE_LIB_OK=TRUE

# Build without PDFs temporarily
nancy-brain build --skip-articles

# Or try with longer timeouts
export TIKA_SERVER_TIMEOUT="300"
nancy-brain build
```

## Quick Fixes for Common Scenarios

### "I just want it to work!" (Emergency Mode)

```bash
# 1. Nuclear option - skip all PDFs
export SKIP_PDF_PROCESSING=true
export KMP_DUPLICATE_LIB_OK=TRUE
nancy-brain build

# 2. Or use repos only
nancy-brain build --repositories-only
```

### "PDFs are driving me crazy!"

```bash
# Build repos first, add PDFs later
nancy-brain build --repositories-only

# Then add PDFs one category at a time
nancy-brain build --category journal_articles
nancy-brain build --category roman_mission
```

### "Everything was working, now it's broken!"

```bash
# Reset environment variables
unset TIKA_SERVER_JAR TIKA_CLIENT_ONLY
export KMP_DUPLICATE_LIB_OK=TRUE
export JAVA_HOME="/opt/homebrew/opt/openjdk"

# Kill any hanging processes
pkill -f "tika-server"
pkill -f "java.*tika"

# Restart from scratch
nancy-brain build --force-update
```

### Invalid Configuration File

If you get configuration errors:

1. **Check YAML syntax:**
   ```bash
   python -c "import yaml; yaml.safe_load(open('config/repositories.yml'))"
   ```

2. **Validate required fields:**
   - Each repository needs `name` and `url`
   - Categories should be properly nested

### Missing Knowledge Base

If the system can't find your knowledge base:

1. **Check paths in configuration**
2. **Ensure directories exist**
3. **Run build process:**
   ```bash
   nancy-brain build --verbose
   ```

## Getting Help

### Diagnostic Information

When reporting issues, include this information:

```bash
# Environment info
echo "OS: $(uname -a)"
echo "Python: $(python --version)"
echo "Java: $(java -version 2>&1 | head -1)"
echo "Conda env: $CONDA_DEFAULT_ENV"

# Nancy Brain info
pip list | grep -E "(nancy-brain|txtai|tika)"

# Environment variables
echo "KMP_DUPLICATE_LIB_OK: $KMP_DUPLICATE_LIB_OK"
echo "JAVA_HOME: $JAVA_HOME"

# Check knowledge base
ls -la knowledge_base/embeddings/ 2>/dev/null || echo "No embeddings found"
```

### Log Files

Check these locations for detailed error logs:
- `tika.log` (if it exists) - Tika server logs
- Terminal output from `nancy-brain build --verbose`
- `~/.nancy-brain/logs/` (if configured)

If you can't resolve an issue:

1. **Check the logs** for detailed error messages
2. **Search existing issues** on GitHub  
3. **Use the troubleshooting notebook:** `docs/knowledge_base_troubleshooting.ipynb`
4. **Create a new issue** with:
   - Error message
   - Steps to reproduce
   - System information (from diagnostic commands above)
   - Configuration files (with sensitive data removed)

## Common Solutions

### Reset Everything

If you're having persistent issues:

```bash
# Remove existing knowledge base
rm -rf knowledge_base/

# Reinstall the package
pip uninstall nancy-brain
pip install nancy-brain

# Rebuild from scratch
nancy-brain build
```

### Update to Latest Version

Many issues are resolved in newer versions:

```bash
pip install --upgrade nancy-brain
```
