# Gemini Code Assist Integration

Nancy Brain can be used as a local MCP (Model Context Protocol) server with Gemini Code Assist, allowing you to interact with your knowledge base directly within your IDE.

!!! info "Using the shared microlensing service?"
    This page documents a locally built instance. Hosted-service connection
    details and generic MCP settings are maintained at
    [nancy.rges-pit.com](https://nancy.rges-pit.com/).

## Prerequisites

Before you begin, ensure you have [installed Nancy Brain](../installation.md)
and built your knowledge base.

## Configuration

To connect Gemini Code Assist to the Nancy Brain MCP server, you need to configure it in your Gemini settings file.

1.  Open your Gemini settings JSON file, located at `~/.gemini/settings.json` (where `~` is your home directory).
2.  Add the following configuration to the `mcpServers` object:

    ```json
    {
        "mcpServers": {
            "nancy-brain": {
                "command": "/path/to/your/conda/env/bin/python",
                "args": [
                    "/path/to/your/nancy-brain/connectors/mcp_server/server.py",
                    "/path/to/your/project/config/repositories.yml",
                    "/path/to/your/project/knowledge_base/embeddings",
                    "--weights",
                    "/path/to/your/project/config/index_weights.yaml"
                ]
            }
        }
    }
    ```

    Replace every placeholder with an absolute path. The server script comes
    from the Nancy Brain source checkout; the configuration, embeddings, and
    weights paths belong to the knowledge-base project you built.

3.  Save the `settings.json` file.
4.  In your IDE, open the command palette and select **Developer: Reload Window** to apply the changes.

## Usage

Once configured, you can interact with the Nancy Brain server in the Gemini Code Assist chat.

-   Use the `/mcp` command to check the status of the `nancy-brain` server and see a list of available tools.
-   Use the `/tools` command to see all available tools, including those from the `nancy-brain` server.

You can now use the Nancy Brain tools, such as `search_knowledge_base`, directly in the Gemini chat to query your knowledge base.

### Example Prompt:

> /search_knowledge_base what is the architecture of this project?

This will use Nancy Brain to search the knowledge base and provide a relevant response.
