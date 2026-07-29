# VS Code and MCP

VS Code supports local stdio servers and remote Streamable HTTP MCP servers.
This page describes connecting to a Nancy Brain instance that you operate.

!!! info "Using the shared microlensing service?"
    Use the ready-to-paste configuration at
    [nancy.rges-pit.com/connect/vscode](https://nancy.rges-pit.com/connect/vscode/).

## Remote server

Run **MCP: Open User Configuration** and add:

```json
{
  "inputs": [
    {
      "type": "promptString",
      "id": "nancy-api-key",
      "description": "Nancy Brain API key",
      "password": true
    }
  ],
  "servers": {
    "nancy-brain": {
      "type": "http",
      "url": "https://YOUR_SERVER/mcp",
      "headers": {
        "X-API-Key": "${input:nancy-api-key}"
      }
    }
  }
}
```

Start the server with **MCP: List Servers** and inspect its output log if the
connection fails.

## Local stdio server

Build the index first, then configure an absolute path to the environment:

```json
{
  "servers": {
    "nancy-brain-local": {
      "type": "stdio",
      "command": "/absolute/path/to/venv/bin/python",
      "args": [
        "/absolute/path/to/nancy-brain/connectors/mcp_server/server.py",
        "/absolute/path/to/config/repositories.yml",
        "/absolute/path/to/knowledge_base/embeddings",
        "--weights",
        "/absolute/path/to/config/index_weights.yaml"
      ]
    }
  }
}
```

Use absolute paths. A local stdio server runs with your user permissions and
can read the paths supplied to it.

## Verify

Ask the agent:

> Search the knowledge base for installation examples, retrieve the strongest
> result, and include its source path.

You should see both a search and retrieval tool call.
