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

### Missing Dependencies

If you get import errors:

```bash
# Install with all optional dependencies
pip install "nancy-brain[all]"
```

## MCP Server Issues

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

## Configuration Issues

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

If you can't resolve an issue:

1. **Check the logs** for detailed error messages
2. **Search existing issues** on GitHub
3. **Create a new issue** with:
   - Error message
   - Steps to reproduce
   - System information (OS, Python version)
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
