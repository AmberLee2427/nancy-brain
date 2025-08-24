# Nancy Brain MCP Server

The Nancy Brain MCP (Model Context Protocol) Server exposes Nancy's RAG functionality as an MCP server, making it available to MCP-compatible clients like Claude Desktop, VS Code, and other AI development tools.

## What is MCP?

The Model Context Protocol (MCP) is an open standard that enables AI assistants to securely access external data and tools. By implementing an MCP server, Nancy's knowledge base becomes accessible to any MCP-compatible client.

## Features

Nancy Brain MCP Server provides the following tools:

### 🔍 search_knowledge_base
Search Nancy's comprehensive knowledge base for relevant documents and code.

**Parameters:**
- `query` (required): Search query text
- `limit` (optional): Maximum number of results (default: 6)
- `toolkit` (optional): Filter by toolkit ("microlensing_tools", "general_tools")
- `doctype` (optional): Filter by document type ("code", "documentation", "notebook")
- `threshold` (optional): Minimum relevance score (default: 0.0)

### 📄 retrieve_document_passage
Retrieve a specific passage from a document by ID and line range.

**Parameters:**
- `doc_id` (required): Document identifier (e.g., "microlensing_tools/MulensModel/README.md")
- `start` (optional): Starting line number, 0-based (default: 0)
- `end` (optional): Ending line number, exclusive

### 📚 retrieve_multiple_passages
Retrieve multiple document passages in a single request.

**Parameters:**
- `items` (required): Array of retrieval items, each with `doc_id`, `start`, and `end`

### 🌳 explore_document_tree
Explore the document tree structure and list available documents.

**Parameters:**
- `path` (optional): Path prefix to filter results (default: "")
- `max_depth` (optional): Maximum depth to traverse (default: 3)

### ⚖️ set_retrieval_weights
Set retrieval weights for specific documents to adjust their search ranking priority.

**Parameters:**
- `doc_id` (required): Specific document ID to set weight for (e.g., "microlensing_tools/MulensModel/README.md")
- `weight` (required): Weight multiplier value (clamped between 0.5-2.0 for stability)
- `namespace` (optional): Namespace for the weight setting (default: "global")
- `ttl_days` (optional): Time-to-live in days for the weight setting

**Note**: This sets weights for individual documents, not entire namespaces. The weight multiplier is automatically clamped between 0.5 and 2.0 to maintain search result stability.

### 🏥 get_system_status
Get Nancy Brain system status and health information.

**Parameters:** None

## Installation & Setup

### Prerequisites

1. **Python Environment**: Ensure you have the `roman-slack-bot` conda environment set up
2. **Knowledge Base**: Build the knowledge base with embeddings
3. **Configuration**: Have a `repositories.yml` config file

### Install MCP Dependencies

```bash
cd /Users/malpas.1/Code/slack-bot/src/nancy-brain
conda run -n roman-slack-bot pip install -e .
```

This will install all dependencies including MCP from the `pyproject.toml` file.

### Build Knowledge Base (if not already done)

```bash
cd /Users/malpas.1/Code/slack-bot/src/nancy-brain
conda run -n roman-slack-bot python scripts/build_knowledge_base.py
```

## Running the Server

### Option 1: Using the Launcher Script

```bash
cd /Users/malpas.1/Code/slack-bot/src/nancy-brain
conda run -n roman-slack-bot python run_mcp_server.py
```

### Option 2: Direct Command Line

```bash
cd /Users/malpas.1/Code/slack-bot/src/nancy-brain
conda run -n roman-slack-bot python -m connectors.mcp_server.server \
    config/repositories.yml \
    knowledge_base/embeddings \
    --weights config/weights.yaml
```

## Client Configuration

### Claude Desktop

Add the following to your Claude Desktop MCP configuration file:

```json
{
  "mcpServers": {
    "nancy-brain": {
      "command": "conda",
      "args": [
        "run", "-n", "roman-slack-bot",
        "python", "/Users/malpas.1/Code/slack-bot/src/nancy-brain/run_mcp_server.py"
      ]
    }
  }
}
```

### VS Code with MCP Extension

Configure the MCP extension to connect to:
- **Server Type**: stdio
- **Command**: `conda run -n roman-slack-bot python run_mcp_server.py`
- **Working Directory**: `/Users/malpas.1/Code/slack-bot/src/nancy-brain`

## Example Usage

Once connected to an MCP client, you can use natural language to interact with Nancy's knowledge base:

### Search Examples
- "Search for information about gravitational microlensing modeling"
- "Find Python code examples for MulensModel"
- "Look for documentation about binary lens modeling"

### Retrieval Examples
- "Get the README file for MulensModel"
- "Show me the first 50 lines of the MulensModel tutorial"
- "Retrieve the installation instructions from multiple packages"

### Tree Exploration Examples
- "Show me the structure of the microlensing_tools directory"
- "List all available documentation files"
- "Browse the MulensModel package structure"

### Weight Management Examples
- "Set a higher weight for the MulensModel README file"
- "Boost the ranking of specific tutorial documents"
- "Adjust document weights with a time limit"

## Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   MCP Client    │    │  Nancy Brain    │    │   RAG Core      │
│  (Claude, etc.) │◄──►│   MCP Server    │◄──►│   Library       │
└─────────────────┘    └─────────────────┘    └─────────────────┘
                                │                        │
                                ▼                        ▼
                       ┌─────────────────┐    ┌─────────────────┐
                       │   MCP Tools     │    │  Knowledge Base │
                       │  • search       │    │  • embeddings   │
                       │  • retrieve     │    │  • raw files    │
                       │  • tree         │    │  • indexes      │
                       │  • weights      │    └─────────────────┘
                       │  • status       │
                       └─────────────────┘
```

## Testing

Run the comprehensive test suite:

```bash
cd /Users/malpas.1/Code/slack-bot/src/nancy-brain
conda run -n roman-slack-bot python -m pytest tests/test_mcp_server.py -v
```

## Troubleshooting

### Server Won't Start
- Verify conda environment is active
- Check that knowledge base embeddings exist
- Ensure repositories.yml config file is present

### No Search Results
- Verify embeddings were built successfully
- Check query spelling and terminology
- Try broader search terms

### Connection Issues
- Ensure MCP client is configured correctly
- Check file paths in configuration
- Verify conda environment name

## Development

### Adding New Tools

1. Add tool definition to `handle_list_tools()`
2. Add handler method (e.g., `_handle_new_tool()`)
3. Add case to `handle_call_tool()`
4. Write tests in `test_mcp_server.py`

### Modifying Tool Behavior

Edit the corresponding `_handle_*` method in `connectors/mcp_server/server.py`.

## Related Documentation

- [RAG Core Library](../rag_core/README.md)
- [HTTP API Connector](../connectors/http_api/README.md)
- [Knowledge Base Management](KNOWLEDGE_BASE_SCRIPTS.md)
- [Model Context Protocol Specification](https://spec.modelcontextprotocol.io/)

## Support

For issues related to the MCP server, check:
1. Server logs for error messages
2. MCP client logs
3. Knowledge base integrity
4. Configuration file validity
