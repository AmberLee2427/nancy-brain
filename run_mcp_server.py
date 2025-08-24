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

    # Default paths (adjust these to match your setup)
    base_path = Path(__file__).parent
    config_path = base_path / "config" / "repositories.yml"
    embeddings_path = base_path / "knowledge_base" / "embeddings"
    weights_path = base_path / "config" / "weights.yaml"

    # Check if paths exist
    missing_paths = []
    if not config_path.exists():
        missing_paths.append(f"Config file: {config_path}")
    if not embeddings_path.exists():
        missing_paths.append(f"Embeddings directory: {embeddings_path}")
    if weights_path and not weights_path.exists():
        # Weights are optional
        weights_path = None

    if missing_paths:
        print("❌ Missing required files:")
        for path in missing_paths:
            print(f"   {path}")
        print("\nPlease ensure you have:")
        print("1. Built the knowledge base with embeddings")
        print("2. Created the repositories.yml config file")
        sys.exit(1)

    print("🚀 Starting Nancy Brain MCP Server...")
    print(f"📂 Config: {config_path}")
    print(f"🔍 Embeddings: {embeddings_path}")
    if weights_path:
        print(f"⚖️ Weights: {weights_path}")
    print("\n🔗 MCP Server ready for connections via stdio")
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
    from connectors.mcp_server.server import NancyMCPServer

    # Create and run server
    server = NancyMCPServer()

    try:
        await server.initialize(config_path, embeddings_path, weights_path)
        await server.run()
    except KeyboardInterrupt:
        print("\n👋 Nancy Brain MCP Server shutting down...")
    except Exception as e:
        print(f"❌ Server error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
