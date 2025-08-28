# VS Code + MCP Integration

Transform VS Code into an AI-powered development environment with access to your Nancy Brain knowledge base through the Model Context Protocol (MCP).

## What You'll Get

- **Smart Code Assistance**: Ask questions about your codebase and get answers from your knowledge base
- **Documentation at Your Fingertips**: Instant access to API docs, tutorials, and examples
- **Context-Aware Suggestions**: AI suggestions based on your specific repositories and documentation
- **Seamless Workflow**: No context switching - everything happens in VS Code

## Prerequisites

- **VS Code** 1.85.0 or later
- **Nancy Brain** installed and knowledge base built
- **MCP-compatible extension** (instructions below)


## VSCode Native Integraion with `Chat` (VSCode version>=1.103.0)

### `Ctrl/Cmd + Shift + P` → "MCP: Add Server..."

#### Option A: Local Command

- Command: /path/to/env/bin/python -m path/to/run_mcp_server.py

- Name: nancy-brain

- Where: Global/Workspace

#### Option B: Pip

- Package name: nancy-brain

- Allow

- Project: path/to/your/project

- env: /path/to/nancy-brain

- KMP_DUPLICATE_LIB_OK

- Name: nancy-brain

- Where: Global/Workspace

#### Option C: Remote HTTP Server

??

`Ctrl/Cmd + Shift + P` → "MCP: Open User Confoguration"

#### Global Settings
A local command example;

```mcp.json
{
  "servers": {
		"nancy-brain": {
			"type": "stdio",
			"command": "/path/to/env/bin/python",
			"args": [
        "-m",
				"/path/to/nancy-brain/run_mcp_server.py"
			],
			"env": {
				"PYTHONPATH": "/path/to/project",
				"KMP_DUPLICATE_LIB_OK": "TRUE"
			}
	  }
	}
}
```

#### Workspace:
A pip example:

```<ws dir>/<ws name>.code-workspace
{
	"folders": [
		{
			"path": "/path/to/project"
		}
	],
	"settings": {
		"mcp.servers": {
			"type": "stdio",
			"command": "uvx",
			"cwd": "${input:cwd}",
			"args": [
				"nancy_brain==0.1.3",
				"/path/to/run_mcp_server.py"
			],
			"env": {
				"KMP_DUPLICATE_LIB_OK": "TRUE"
			}
		}
	}
}
```
^ this doesn't actually work with those settings

---

# For Older Versions of VSCode

## Step 1: Install MCP Extension

Install an MCP-compatible VS Code extension. Popular options:

### Option A: Continue (Recommended)
```bash
# Install the Continue extension
code --install-extension continue.continue
```

### Option B: Codeium
```bash
# Install Codeium extension  
code --install-extension codeium.codeium
```

### Option C: Gemini Code Assist
```bash
code --install-extension gemini-code-assist.gemini-code-assist
```

> For dedicated Gemini Code Assist Instruction see [this page.](https://amberlee2427.github.io/nancy-brain/integrations/gemini-code-assist/)

## Step 2: Build Your Knowledge Base

If you haven't already, create and build a knowledge base:

```bash
# Create a knowledge base for your project
nancy-brain init my-project-kb
cd my-project-kb

# Add relevant repositories
nancy-brain add-repo https://github.com/your-org/main-project.git
nancy-brain add-repo https://github.com/your-framework/docs.git

# Build the embeddings
nancy-brain build
```

## Step 3: Configure MCP Connection

### For Continue Extension

1. **Open Continue Settings**: `Ctrl/Cmd + Shift + P` → "Continue: Open config.json"

2. **Add Nancy Brain MCP Server**:
```json
{
  "models": [
    {
      "title": "Claude 3.5 Sonnet + Nancy Brain",
      "provider": "anthropic",
      "model": "claude-3-5-sonnet-20241022",
      "apiKey": "your-anthropic-api-key"
    }
  ],
  "mcpServers": {
    "nancy-brain": {
      "command": "nancy-brain",
      "args": ["serve", "--mcp"],
      "cwd": "/path/to/your/knowledge-base"
    }
  },
  "contextProviders": [
    {
      "name": "mcp",
      "params": {
        "serverName": "nancy-brain"
      }
    }
  ]
}
```

or, for gemini-code-assist

```~/.gemini/settings.json
{
  "mcpServers": {
    "nancy-brain": {
      "command": "/path/to/env/bin/python",
      "args": [
        "/path/to/nancy-brain/run_mcp_server.py"
      ],
      "env": {
        "PYTHONPATH": "/path/to/project",
        "KMP_DUPLICATE_LIB_OK": "TRUE"
      }
    }
  },
  "ideMode": true,
  "hasSeenIdeIntegrationNudge": true,
  "selectedAuthType": "oauth-personal"
}
```

3. **Restart VS Code** to load the new configuration

### For Codeium Extension

1. **Open Codeium Settings**: VS Code Settings → Extensions → Codeium

2. **Add MCP Server**: In the MCP Servers section:
   - **Name**: `nancy-brain`
   - **Command**: `nancy-brain serve --mcp`
   - **Working Directory**: `/path/to/your/knowledge-base`

## Step 4: Test the Integration

### Basic Search Test

1. **Open the AI Chat**: `Ctrl/Cmd + Shift + P` → "Continue: Open Chat" (or equivalent)

2. **Test a query**:
```
Search the knowledge base for "authentication examples"
```

You should see results from your indexed repositories.

### Code Context Test

1. **Open a code file** in your project

2. **Ask a contextual question**:
```
How do I implement error handling similar to what's shown in the knowledge base?
```

The AI should respond with examples from your indexed documentation.

## Example Workflows

### Documentation Lookup

```
User: How do I configure logging in this framework?

AI: Based on your knowledge base, here are the logging configuration options:

[Results from framework documentation]

Would you like me to show you how to implement this in your current file?
```

### Code Examples

```
User: Show me an example of using the API client

AI: Here's an example from your knowledge base:

[Code snippet from indexed repository]

This shows the typical pattern used in your codebase. Would you like me to adapt this for your current context?
```

### Architecture Questions

```
User: What's the recommended way to structure database models?

AI: According to your project documentation:

[Architecture guidelines from knowledge base]

I can help you implement this pattern in your current file.
```

## Advanced Configuration

### Custom Tool Access

Enable specific Nancy Brain tools:

```json
{
  "mcpServers": {
    "nancy-brain": {
      "command": "nancy-brain",
      "args": ["serve", "--mcp", "--tools", "search,retrieve,explore"],
      "cwd": "/path/to/your/knowledge-base",
      "env": {
        "NANCY_LOG_LEVEL": "info"
      }
    }
  }
}
```

### Multiple Knowledge Bases

Connect to different knowledge bases:

```json
{
  "mcpServers": {
    "nancy-frontend": {
      "command": "nancy-brain",
      "args": ["serve", "--mcp"],
      "cwd": "/path/to/frontend-kb"
    },
    "nancy-backend": {
      "command": "nancy-brain", 
      "args": ["serve", "--mcp"],
      "cwd": "/path/to/backend-kb"
    }
  }
}
```

### Performance Tuning

Optimize for your workflow:

```json
{
  "mcpServers": {
    "nancy-brain": {
      "command": "nancy-brain",
      "args": [
        "serve", "--mcp",
        "--cache-size", "1000",
        "--timeout", "30"
      ]
    }
  }
}
```

## Troubleshooting

### MCP Server Won't Start

**Check Nancy Brain installation**:
```bash
nancy-brain --version
nancy-brain serve --help
```

**Verify knowledge base**:
```bash
cd /path/to/your/knowledge-base
ls knowledge_base/embeddings/
```

**Check VS Code logs**:
- Open VS Code Developer Tools: `Help → Toggle Developer Tools`
- Look for MCP connection errors in the console

### No Search Results

**Test search directly**:
```bash
cd /path/to/your/knowledge-base
nancy-brain search "test query"
```

**Check knowledge base content**:
```bash
nancy-brain explore --max-depth 2
```

### Connection Timeouts

**Increase timeout in config**:
```json
{
  "mcpServers": {
    "nancy-brain": {
      "command": "nancy-brain",
      "args": ["serve", "--mcp", "--timeout", "60"]
    }
  }
}
```

### Permission Issues

**Check file permissions**:
```bash
chmod -R 755 /path/to/your/knowledge-base
```

## Tips for Best Results

### 1. Organize Your Knowledge Base
- Use clear repository names
- Include relevant documentation repositories
- Keep the knowledge base focused on your current project

### 2. Use Specific Queries
- ❌ "How do I code?"
- ✅ "How do I implement JWT authentication in this API?"

### 3. Leverage Context
- Have relevant files open in VS Code
- The AI can use both your current code and knowledge base

### 4. Update Regularly
```bash
# Refresh your knowledge base periodically
nancy-brain build --force-update
```

## What's Next?

- **[Claude Desktop Integration](claude-desktop.md)** - Use Nancy Brain with Claude Desktop
- **[Python API](../tutorials/python-api.md)** - Build custom integrations
- **[Architecture Guide](../development/architecture.md)** - Understand how it all works

## Need Help?

- Check the [troubleshooting section](../reference/mcp-server-original.md#troubleshooting)
- Open an issue on [GitHub](https://github.com/AmberLee2427/nancy-brain/issues)
- Join the discussion in [GitHub Discussions](https://github.com/AmberLee2427/nancy-brain/discussions)
