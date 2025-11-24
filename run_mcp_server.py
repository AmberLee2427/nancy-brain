#!/usr/bin/env python3
"""
Nancy Brain MCP Server Launcher

This script provides an easy way to launch the Nancy Brain MCP server
with the correct configuration and paths.

Prerequisites:
    conda run -n roman-slack-bot pip install -e .

Usage:
    python run_mcp_server.py
"""

import os

# Fix OpenMP issue before importing any ML libraries
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

import sys
import asyncio
from pathlib import Path

# Add the current directory to path so we can import our modules
sys.path.insert(0, str(Path(__file__).parent))


async def main():
    """Launch the Nancy Brain MCP server with default configuration."""

    port = int(os.environ.get("MCP_PORT", "8000"))

    # Default paths (adjust these to match your setup)
    base_path = Path(__file__).parent
    config_path = base_path / "config" / "repositories.yml"
    embeddings_path = base_path / "knowledge_base" / "embeddings"
    weights_path = base_path / "config" / "index_weights.yaml"

    # Check if paths exist
    missing_paths = []
    if not config_path.exists():
        missing_paths.append(f"Config file: {config_path}")
    if not embeddings_path.exists():
        missing_paths.append(f"Embeddings directory: {embeddings_path}")
    if weights_path and not weights_path.exists():
        print(f"❌ Weights file not found: {weights_path}")
        sys.exit(1)

    if missing_paths:
        print("❌ Missing required files:")
        for path in missing_paths:
            print(f"   {path}")
        print("\nPlease ensure you have:")
        print("1. Built the knowledge base with embeddings")
        print("2. Created the repositories.yml config file")
        sys.exit(1)

    # Validate that the weights file is NOT a model weights file (should not contain per-document weights)
    import yaml

    try:
        with open(weights_path, "r") as f:
            data = yaml.safe_load(f) or {}
            forbidden_keys = {"model_weights", "doc_weights", "documents"}
            if any(k in data for k in forbidden_keys):
                print(
                    f"❌ ERROR: The weights file '{weights_path}' appears to be a model weights file (contains {forbidden_keys}). Please provide an index_weights.yaml file for extension/path weights only."
                )
                sys.exit(1)
    except Exception as e:
        print(f"❌ Failed to validate weights file: {e}")
        sys.exit(1)

    print("🚀 Starting Nancy Brain MCP Server...")
    print(f"📂 Config: {config_path}")
    print(f"🔍 Embeddings: {embeddings_path}")
    if weights_path:
        print(f"⚖️ Weights: {weights_path}")
    print("\n🔗 MCP Server ready for connections via stdio and/or HTTP")
    print("💡 Connect this server to Claude Desktop, VS Code, or other MCP clients")
    print("\n📋 Available tools:")
    print("   • search_knowledge_base - Search Nancy's knowledge base")
    print("   • retrieve_document_passage - Get specific document sections")
    print("   • retrieve_multiple_passages - Batch retrieve documents")
    print("   • explore_document_tree - Browse the document structure")
    print("   • set_retrieval_weights - Adjust search priorities")
    print("   • get_system_status - Check server health and version")
    print("\n" + "=" * 60)

    # Import here to avoid early crashes with txtai/torch
    import subprocess
    import sys

    # Always use connectors/mcp_server/server.py as the real entrypoint for HTTP/stdio
    server_script = str(Path(__file__).parent / "connectors/mcp_server/server.py")
    args = [
        sys.executable,
        server_script,
        str(config_path),
        str(embeddings_path),
        "--weights",
        str(weights_path),
        "--port",
        str(port),
        "--http-and-stdio",
    ]
    try:
        proc = subprocess.Popen(args)
        proc.wait()
    except KeyboardInterrupt:
        print("\n👋 Nancy Brain MCP Server shutting down...")
    except Exception as e:
        print(f"❌ Server error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
