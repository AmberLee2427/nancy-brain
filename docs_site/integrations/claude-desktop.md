# Claude Desktop Integration

Nancy Brain integrates seamlessly with Claude Desktop through the Model Context Protocol (MCP), giving you AI-powered access to your knowledge bases directly in conversations with Claude.

## Overview

The Nancy Brain MCP server provides Claude with these capabilities:

- **🔍 Search** your knowledge base with natural language queries
- **📖 Retrieve** specific document passages with line-level precision  
- **🌳 Explore** the document tree structure to understand your knowledge base
- **⚖️ Weight** documents dynamically to prioritize certain sources
- **📊 Monitor** system status and health

## Quick Setup

### 1. Install Nancy Brain

```bash
pip install nancy-brain
```

### 2. Build Your Knowledge Base

```bash
# Initialize project
nancy-brain init my-research-kb
cd my-research-kb

# Configure repositories in config/repositories.yml
# Then build
nancy-brain build
```

### 3. Configure Claude Desktop

Add Nancy Brain to your Claude Desktop MCP configuration:

**macOS/Linux:** `~/.config/claude/claude_desktop_config.json`  
**Windows:** `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "nancy-brain": {
      "command": "nancy-brain-mcp",
      "args": [
        "--embeddings-path", "/path/to/your/knowledge_base/embeddings",
        "--config", "/path/to/your/config/repositories.yml",
        "--weights", "/path/to/your/config/weights.yaml"
      ]
    }
  }
}
```

### 4. Restart Claude Desktop

Close and reopen Claude Desktop. You should see Nancy Brain listed in the MCP servers section.

## Detailed Configuration

### Configuration Options

The MCP server accepts these command-line arguments:

| Argument | Description | Default |
|----------|-------------|---------|
| `--embeddings-path` | Path to embeddings directory | `knowledge_base/embeddings` |
| `--config` | Repository configuration file | `config/repositories.yml` |
| `--weights` | Model weights configuration | `config/weights.yaml` |
| `--host` | Host to bind to | `127.0.0.1` |
| `--port` | Port to bind to | `8765` |

### Example Configurations

**Basic Research Setup:**
```json
{
  "mcpServers": {
    "research-kb": {
      "command": "nancy-brain-mcp",
      "args": [
        "--embeddings-path", "/Users/researcher/microlensing-kb/knowledge_base/embeddings",
        "--config", "/Users/researcher/microlensing-kb/config/repositories.yml"
      ]
    }
  }
}
```

**Multi-Project Setup:**
```json
{
  "mcpServers": {
    "astro-tools": {
      "command": "nancy-brain-mcp",
      "args": [
        "--embeddings-path", "/path/to/astro-tools/embeddings",
        "--config", "/path/to/astro-tools/config.yml"
      ]
    },
    "ml-research": {
      "command": "nancy-brain-mcp",
      "args": [
        "--embeddings-path", "/path/to/ml-research/embeddings", 
        "--config", "/path/to/ml-research/config.yml"
      ]
    }
  }
}
```

**Custom Network Configuration:**
```json
{
  "mcpServers": {
    "nancy-brain": {
      "command": "nancy-brain-mcp",
      "args": [
        "--embeddings-path", "./embeddings",
        "--host", "0.0.0.0",
        "--port", "9000"
      ]
    }
  }
}
```

## Using Nancy Brain with Claude

Once configured, you can interact with your knowledge base through natural conversation with Claude.

### Basic Search Examples

**Research Questions:**
> "Search my knowledge base for information about microlensing detection algorithms"

**Technical Queries:**
> "Find documentation about binary lens modeling in MulensModel"

**Comparative Analysis:**
> "Search for performance comparisons between different optimization algorithms"

### Advanced Usage Patterns

**Literature Review:**
> "I'm writing a review on exoplanet detection methods. Search for recent papers on microlensing techniques and summarize the key approaches."

**Code Understanding:**
> "I need to understand how finite source effects are implemented. Search for relevant code and documentation, then explain the mathematical approach."

**Method Development:**
> "I'm developing a new machine learning approach for microlensing event classification. Search for existing ML implementations in astronomical time series analysis."

**Debugging Help:**
> "I'm getting numerical instabilities in my lens equation solver. Search for discussion of numerical methods and precision issues in microlensing codes."

### Document Exploration

**Browse Structure:**
> "Show me the document tree structure for the MulensModel repository"

**Focused Exploration:**  
> "Explore the documentation section of pyLIMA to understand the available tutorials"

**Find Specific Files:**
> "List all Python files in the examples directory of VBMicrolensing"

### Retrieval and Analysis

**Get Specific Documentation:**
> "Retrieve the full text of the MulensModel installation guide"

**Compare Implementations:**
> "Get the documentation for the Event class in both MulensModel and pyLIMA, then compare their capabilities"

**Extract Code Examples:**
> "Find and retrieve example scripts that demonstrate binary lens fitting"

## Available MCP Tools

Nancy Brain provides these tools to Claude:

### search_knowledge_base
Search your knowledge base with natural language queries.

**Parameters:**
- `query` (required) - Search query string
- `limit` (optional) - Number of results (default: 6) 
- `toolkit` (optional) - Filter by toolkit/category
- `doctype` (optional) - Filter by document type
- `threshold` (optional) - Minimum relevance score

### retrieve_document_passage  
Retrieve specific text from a document.

**Parameters:**
- `doc_id` (required) - Document identifier
- `start` (optional) - Starting line number
- `end` (optional) - Ending line number

### retrieve_multiple_passages
Retrieve multiple document passages in a single request.

**Parameters:**
- `items` (required) - List of retrieval requests

### explore_document_tree
Explore the knowledge base structure.

**Parameters:**
- `path` (optional) - Path prefix to filter results
- `max_depth` (optional) - Maximum tree depth (default: 3)

### set_retrieval_weights
Adjust document weights for prioritization.

**Parameters:**
- `namespace` (required) - Namespace to weight
- `weight` (required) - Weight value (higher = more priority)

### get_system_status
Get Nancy Brain system status and health information.

## Conversation Examples

### Example 1: Research Overview

**You:** "I'm new to microlensing research. Can you search my knowledge base and give me an overview of the main analysis tools available?"

**Claude:** *Uses search_knowledge_base to find relevant documentation, then provides comprehensive overview of MulensModel, pyLIMA, VBMicrolensing, etc.*

### Example 2: Implementation Help

**You:** "I need to implement finite source effects in my microlensing model. Can you find relevant code and explain the approach?"

**Claude:** *Searches for finite source implementations, retrieves specific code sections, and explains the mathematical and computational approaches*

### Example 3: Literature Analysis

**You:** "Search for papers discussing systematic uncertainties in galactic bulge microlensing surveys and summarize the main sources of error."

**Claude:** *Searches knowledge base for relevant papers, retrieves key sections, and provides structured summary of systematic uncertainty sources*

### Example 4: Code Debugging

**You:** "My binary lens caustic calculation is giving weird results near the planetary caustic. Search for discussions of numerical precision issues in binary lens codes."

**Claude:** *Searches for relevant technical discussions, finds implementation details, and suggests debugging approaches*

## Tips for Effective Usage

### Writing Better Queries

**Be Specific:**
- ✅ "Search for neural network implementations in astronomical time series analysis"
- ❌ "Search for AI stuff"

**Use Technical Terms:**
- ✅ "Find documentation about MCMC parameter estimation in microlensing"
- ❌ "Find info about statistics"

**Combine Concepts:**
- ✅ "Search for GPU acceleration methods in large-scale astronomical surveys"
- ❌ "Search for fast computing"

### Leveraging Document Structure

**Explore First:**
> "Show me the structure of the MulensModel documentation before I ask specific questions"

**Use Hierarchical Queries:**
> "First explore the examples directory, then retrieve the binary lens fitting tutorial"

**Filter by Type:**
> "Search only documentation files for installation instructions"

### Working with Large Results

**Iterate and Refine:**
> "That search returned too many results. Can you search specifically for 'optimization algorithms' in the MulensModel repository?"

**Use Multiple Searches:**
> "Search for 'finite source' in the theoretical papers, then search for 'finite source implementation' in the code repositories"

**Prioritize Sources:**
> "Increase the weight for MulensModel documentation, then search for event fitting tutorials"

## Troubleshooting

### MCP Server Not Starting

**Check Configuration:**
```bash
# Test MCP server manually
nancy-brain-mcp --embeddings-path ./knowledge_base/embeddings

# Verify paths exist
ls -la knowledge_base/embeddings/
ls -la config/repositories.yml
```

**Common Issues:**
- Incorrect file paths in configuration
- Knowledge base not built (`nancy-brain build`)
- Missing dependencies (`pip install nancy-brain`)

### No Search Results

**Verify Knowledge Base:**
```bash
# Check if embeddings exist
nancy-brain explore --max-entries 10

# Test search directly
nancy-brain search "test query"
```

**Common Issues:**
- Empty knowledge base (run `nancy-brain build`)
- Query too specific (try broader terms first)
- Wrong embeddings path in configuration

### Performance Issues

**Optimize Configuration:**
- Use local paths (avoid network drives)
- Ensure adequate RAM for large knowledge bases
- Consider using SSD storage for embeddings

**Debug Performance:**
```bash
# Check system status
nancy-brain search "status" --limit 1

# Monitor resource usage
top -p $(pgrep nancy-brain-mcp)
```

### Claude Not Recognizing MCP Server

**Restart Claude Desktop:**
- Close completely and reopen
- Check MCP server status in Claude settings

**Verify Configuration:**
```json
// Ensure proper JSON formatting
{
  "mcpServers": {
    "nancy-brain": {
      "command": "nancy-brain-mcp",
      "args": ["--embeddings-path", "/full/absolute/path"]
    }
  }
}
```

## Advanced Integration

### Multiple Knowledge Bases

Configure separate MCP servers for different research areas:

```json
{
  "mcpServers": {
    "astro-tools": {
      "command": "nancy-brain-mcp",
      "args": ["--embeddings-path", "/path/to/astro/embeddings"]
    },
    "ml-papers": {
      "command": "nancy-brain-mcp", 
      "args": ["--embeddings-path", "/path/to/ml/embeddings"]
    }
  }
}
```

Then specify which to use:
> "Search the astro-tools knowledge base for optimization algorithms"

### Custom Weights Configuration

Create `config/weights.yaml` to prioritize certain content:

```yaml
# Boost certain file types
file_weights:
  ".py": 1.2      # Python code
  ".md": 1.1      # Documentation
  ".rst": 1.1     # Sphinx docs
  ".ipynb": 1.0   # Notebooks
  ".txt": 0.8     # Plain text

# Boost certain repositories
repo_weights:
  "MulensModel": 1.3
  "pyLIMA": 1.2
  "astropy": 1.1
```

### Integration with Development Workflow

**Code Review Assistant:**
> "I'm reviewing a pull request that adds finite source effects. Search for existing implementations and best practices."

**Documentation Helper:**
> "I'm writing documentation for my new function. Search for good examples of function documentation in similar libraries."

**Research Planning:**
> "I want to implement a new optimization algorithm. Search for performance benchmarks of existing methods."

## Security Considerations

### Local vs Remote Access

**Local Access (Recommended):**
- MCP server runs locally
- All data stays on your machine
- Fastest performance

**Network Access:**
- Use `--host 0.0.0.0` for network access
- Consider firewall implications
- Secure networks only

### Data Privacy

- Knowledge base data never leaves your system
- Claude Desktop communicates with local MCP server
- No external API calls for search/retrieval

### Access Control

- MCP server has read-only access to your knowledge base
- No modification capabilities through Claude interface
- Standard file system permissions apply

## Next Steps

1. **Build Your Knowledge Base**: Follow [Quick Start Guide](../quick-start.md)
2. **Customize Configuration**: See [Configuration Guide](../configuration.md)  
3. **Explore Advanced Features**: Try [Research Workflow Tutorial](../tutorials/research-workflow.md)
4. **Integrate with VS Code**: Set up [VS Code MCP Extension](./vscode-mcp.md)
5. **Automate Updates**: Create scripts for regular knowledge base updates

## Further Reading

- [MCP Server Documentation](../reference/mcp-server-original.md) - Technical details
- [HTTP API Reference](./http-api.md) - Alternative access methods
- [CLI Reference](../api/cli.md) - Command-line usage
- [Troubleshooting Guide](../development/troubleshooting.md) - Common issues
