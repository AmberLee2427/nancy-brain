# Gemini Code Assist Integration

Nancy Brain can be used as a local MCP (Model Context Protocol) server with Gemini Code Assist, allowing you to interact with your knowledge base directly within your IDE.

## Prerequisites

Before you begin, ensure you have [installed Nancy Brain](https://github.com/AmberLee2427/nancy-brain/blob/main/INSTALLATION.md) and built your knowledge base.

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
                    "/path/to/your/slack-bot/src/nancy-brain/run_mcp_server.py"
                ],
                "env": {
                    "PYTHONPATH": "/path/to/your/slack-bot/src/nancy-brain",
                    "KMP_DUPLICATE_LIB_OK": "TRUE"
                }
            }
        }
    }
    ```

    **Important:** Replace `/path/to/your/conda/env/bin/python` with the absolute path to the Python executable in your Conda environment where `nancy-brain` is installed. Also, replace `/path/to/your/slack-bot/` with the absolute path to your `slack-bot` project directory.

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
