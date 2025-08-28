#!/usr/bin/env python3
"""
Nancy Brain MCP Server

A Model Context Protocol server that exposes Nancy's RAG (Retrieval-Augmented Generation)
fun                types.Tool(
                    name="set_retrieval_weights",
                    description="Set retrieval weights for specific documents to adjust their search ranking priority",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "doc_id": {
                                "type": "string",
                                "description": "Specific document ID to set weight for (e.g., 'microlensing_tools/MulensModel/README.md')"
                            },
                            "weight": {
                                "type": "number",
                                "description": "Weight multiplier value (will be clamped between 0.5-2.0)",
                                "minimum": 0.1,
                                "maximum": 5.0
                            },
                            "namespace": {
                                "type": "string",
                                "description": "Namespace for the weight setting",
                                "default": "global"
                            },
                            "ttl_days": {
                                "type": "integer",
                                "description": "Time-to-live in days for the weight setting",
                                "minimum": 1
                            }
                        },
                        "required": ["doc_id", "weight"]
                    }
                ),with MCP-compatible clients like Claude Desktop, VS Code, and other AI tools.

This server provides tools for:
- Searching through Nancy's knowledge base
- Retrieving specific document passages
- Exploring the document tree structure
- Managing retrieval weights and priorities

Usage:
    python -m connectors.mcp_server.server [config_path] [embeddings_path] [weights_path]
"""

import os

# Fix OpenMP issue before importing any ML libraries
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"

import sys
import asyncio
import argparse
from pathlib import Path
from typing import Any, Dict, List, Optional

from mcp.server import Server, InitializationOptions, NotificationOptions
from mcp import types
from mcp import stdio_server

from rag_core.service import RAGService


class NancyMCPServer:
    """Nancy Brain MCP Server implementation."""

    def __init__(self):
        self.server = Server("nancy-brain")
        self.rag_service: Optional[RAGService] = None
        self._setup_handlers()

    def _setup_handlers(self):
        """Set up MCP server handlers."""

        @self.server.list_tools()
        async def handle_list_tools() -> list[types.Tool]:
            """List available tools."""
            return [
                types.Tool(
                    name="search_knowledge_base",
                    description="Search Nancy's knowledge base for relevant documents and code",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "Search query for the knowledge base",
                            },
                            "limit": {
                                "type": "integer",
                                "description": "Maximum number of results to return",
                                "default": 6,
                            },
                            "toolkit": {
                                "type": "string",
                                "description": "Filter by specific toolkit/category",
                                "enum": ["microlensing_tools", "general_tools"],
                            },
                            "doctype": {
                                "type": "string",
                                "description": "Filter by document type",
                                "enum": ["code", "documentation", "notebook"],
                            },
                            "threshold": {
                                "type": "number",
                                "description": "Minimum relevance score threshold",
                                "default": 0.0,
                            },
                        },
                        "required": ["query"],
                    },
                ),
                types.Tool(
                    name="retrieve_document_passage",
                    description="Retrieve a specific passage from a document by ID and line range",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "doc_id": {
                                "type": "string",
                                "description": "Document ID (e.g., 'microlensing_tools/MulensModel/README.md')",
                            },
                            "start": {
                                "type": "integer",
                                "description": "Starting line number (0-based)",
                                "default": 0,
                            },
                            "end": {
                                "type": "integer",
                                "description": "Ending line number (exclusive)",
                            },
                        },
                        "required": ["doc_id"],
                    },
                ),
                types.Tool(
                    name="retrieve_multiple_passages",
                    description="Retrieve multiple document passages in a single request",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "items": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "doc_id": {"type": "string"},
                                        "start": {"type": "integer", "default": 0},
                                        "end": {"type": "integer"},
                                    },
                                    "required": ["doc_id"],
                                },
                                "description": "List of document passages to retrieve",
                            }
                        },
                        "required": ["items"],
                    },
                ),
                types.Tool(
                    name="explore_document_tree",
                    description="Explore the document tree structure and list available documents",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "path": {
                                "type": "string",
                                "description": "Path prefix to filter results (e.g., 'microlensing_tools/MulensModel')",
                                "default": "",
                            },
                            "max_depth": {
                                "type": "integer",
                                "description": "Maximum depth to traverse",
                                "default": 3,
                            },
                        },
                    },
                ),
                types.Tool(
                    name="set_retrieval_weights",
                    description="Set retrieval weights to prioritize certain namespaces or document types",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "namespace": {
                                "type": "string",
                                "description": "Namespace to set weight for (e.g., 'microlensing_tools')",
                            },
                            "weight": {
                                "type": "number",
                                "description": "Weight value (higher = more priority)",
                                "minimum": 0.0,
                            },
                        },
                        "required": ["namespace", "weight"],
                    },
                ),
                types.Tool(
                    name="get_system_status",
                    description="Get Nancy Brain system status and health information",
                    inputSchema={"type": "object", "properties": {}},
                ),
            ]

        @self.server.call_tool()
        async def handle_call_tool(
            name: str, arguments: Dict[str, Any]
        ) -> list[types.TextContent | types.ImageContent | types.EmbeddedResource]:
            """Handle tool calls."""
            if not self.rag_service:
                return [
                    types.TextContent(
                        type="text",
                        text="❌ Nancy Brain service not initialized. Please check server configuration.",
                    )
                ]

            try:
                if name == "search_knowledge_base":
                    return await self._handle_search(arguments)
                elif name == "retrieve_document_passage":
                    return await self._handle_retrieve(arguments)
                elif name == "retrieve_multiple_passages":
                    return await self._handle_retrieve_batch(arguments)
                elif name == "explore_document_tree":
                    return await self._handle_tree(arguments)
                elif name == "set_retrieval_weights":
                    return await self._handle_set_weights(arguments)
                elif name == "get_system_status":
                    return await self._handle_status(arguments)
                else:
                    return [types.TextContent(type="text", text=f"❌ Unknown tool: {name}")]
            except Exception as e:
                return [types.TextContent(type="text", text=f"❌ Error executing {name}: {str(e)}")]

    async def _handle_search(self, args: Dict[str, Any]) -> list[types.TextContent]:
        """Handle search_knowledge_base tool."""
        if not self.rag_service:
            return [
                types.TextContent(
                    type="text",
                    text="❌ Nancy Brain service not initialized. Please check server configuration.",
                )
            ]

        query = args["query"]
        limit = args.get("limit", 6)
        toolkit = args.get("toolkit")
        doctype = args.get("doctype")
        threshold = args.get("threshold", 0.0)

        results = await self.rag_service.search_docs(
            query=query,
            limit=limit,
            toolkit=toolkit,
            doctype=doctype,
            threshold=threshold,
        )

        if not results:
            return [types.TextContent(type="text", text=f"🔍 No results found for query: '{query}'")]

        # Format results
        response_text = f"🔍 **Search Results for:** '{query}'\n\n"

        for i, result in enumerate(results, 1):
            score = result.get("score", 0.0)
            doc_id = result.get("id", result.get("doc_id", "unknown"))
            text = result.get("text", "")

            response_text += f"**{i}. {doc_id}** (score: {score:.3f})\n"
            response_text += f"```\n{text[:300]}{'...' if len(text) > 300 else ''}\n```\n\n"

        return [types.TextContent(type="text", text=response_text)]

    async def _handle_retrieve(self, args: Dict[str, Any]) -> list[types.TextContent]:
        """Handle retrieve_document_passage tool."""
        doc_id = args["doc_id"]
        start = args.get("start", 0)
        end = args.get("end")

        result = await self.rag_service.retrieve(doc_id, start, end)

        if not result:
            return [types.TextContent(type="text", text=f"❌ Document not found: {doc_id}")]

        text = result.get("text", "")
        github_url = result.get("github_url", "")

        response_text = f"📄 **Document:** {doc_id}\n"
        if github_url:
            response_text += f"🔗 **GitHub:** {github_url}\n"
        response_text += f"\n```\n{text}\n```"

        return [types.TextContent(type="text", text=response_text)]

    async def _handle_retrieve_batch(self, args: Dict[str, Any]) -> list[types.TextContent]:
        """Handle retrieve_multiple_passages tool."""
        items = args["items"]

        results = await self.rag_service.retrieve_batch(items)

        if not results:
            return [types.TextContent(type="text", text="❌ No documents retrieved")]

        response_text = f"📄 **Retrieved {len(results)} passages:**\n\n"

        for i, result in enumerate(results, 1):
            doc_id = result.get("doc_id", "unknown")
            text = result.get("text", "")
            github_url = result.get("github_url", "")

            response_text += f"**{i}. {doc_id}**\n"
            if github_url:
                response_text += f"🔗 {github_url}\n"
            response_text += f"```\n{text}\n```\n\n"

        return [types.TextContent(type="text", text=response_text)]

    async def _handle_tree(self, args: Dict[str, Any]) -> list[types.TextContent]:
        """Handle explore_document_tree tool."""
        path = args.get("path", "")
        max_depth = args.get("max_depth", 3)

        tree_data = await self.rag_service.list_tree(path, max_depth)

        response_text = "🌳 **Document Tree"
        if path:
            response_text += f" (path: {path})"
        response_text += ":**\n\n"

        def format_tree(items, indent=0):
            formatted = ""
            for item in items[:50]:  # Limit for readability
                prefix = "  " * indent
                if isinstance(item, dict):
                    name = item.get("name", "unknown")
                    if item.get("type") == "file":
                        formatted += f"{prefix}📄 {name}\n"
                    else:
                        formatted += f"{prefix}📁 {name}/\n"
                        if "children" in item:
                            formatted += format_tree(item["children"], indent + 1)
                else:
                    formatted += f"{prefix}📄 {item}\n"
            return formatted

        response_text += format_tree(tree_data)

        return [types.TextContent(type="text", text=response_text)]

    async def _handle_set_weights(self, args: Dict[str, Any]) -> list[types.TextContent]:
        """Handle set_retrieval_weights tool."""
        if not self.rag_service:
            return [
                types.TextContent(
                    type="text",
                    text="❌ Nancy Brain service not initialized. Please check server configuration.",
                )
            ]

        doc_id = args["doc_id"]
        weight = args["weight"]
        namespace = args.get("namespace", "global")
        ttl_days = args.get("ttl_days")

        await self.rag_service.set_weight(doc_id, weight, namespace, ttl_days)

        # Show the actual clamped weight
        clamped_weight = max(0.5, min(weight, 2.0))

        response_text = "⚖️ **Weight Updated:**\n"
        response_text += f"Document: `{doc_id}`\n"
        response_text += f"Requested Weight: `{weight}`\n"
        if clamped_weight != weight:
            response_text += f"Actual Weight: `{clamped_weight}` (clamped to safe range 0.5-2.0)\n"
        else:
            response_text += f"Applied Weight: `{weight}`\n"
        response_text += f"Namespace: `{namespace}`\n"
        if ttl_days:
            response_text += f"TTL: `{ttl_days}` days\n"
        response_text += "\nThis will adjust the document's ranking in future searches."

        return [types.TextContent(type="text", text=response_text)]

    async def _handle_status(self, args: Dict[str, Any]) -> list[types.TextContent]:
        """Handle get_system_status tool."""
        if not self.rag_service:
            return [types.TextContent(type="text", text="❌ Nancy Brain service not initialized.")]

        # Use the merged system status (health + version + env + dependencies)
        try:
            status_info = await self.rag_service.system_status() if hasattr(self.rag_service, "system_status") else None
        except Exception:
            status_info = None
        health_info = None
        if not status_info:
            # Fallback: merge health and version manually
            health_info = await self.rag_service.health()
            version_info = await self.rag_service.version()
            status_info = {
                **version_info,
                "status": health_info.get("status", "unknown"),
                "registry_loaded": health_info.get("registry_loaded"),
                "store_loaded": health_info.get("store_loaded"),
                "search_loaded": health_info.get("search_loaded"),
            }
        else:
            # If system_status exists, try to get health info for details
            try:
                health_info = await self.rag_service.health()
            except Exception:
                health_info = None

        response_text = "🏥 **Nancy Brain System Status**\n\n"
        status = status_info.get("status", "unknown")
        status_emoji = "✅" if status == "ok" else "❌"
        response_text += f"{status_emoji} **Status:** {status}\n"

        # Add subsystem details
        registry_loaded = status_info.get("registry_loaded")
        store_loaded = status_info.get("store_loaded")
        search_loaded = status_info.get("search_loaded")
        # If not present, try to get from health_info
        if registry_loaded is None and health_info:
            registry_loaded = health_info.get("registry_loaded")
        if store_loaded is None and health_info:
            store_loaded = health_info.get("store_loaded")
        if search_loaded is None and health_info:
            search_loaded = health_info.get("search_loaded")

        def checkmark(val):
            return "✅" if val else "❌"

        response_text += "\n**Subsystems:**\n"
        response_text += f"- Registry: {checkmark(registry_loaded)}\n"
        response_text += f"- Store: {checkmark(store_loaded)}\n"
        response_text += f"- Search: {checkmark(search_loaded)}\n"

        response_text += f"\n🏷️ **Version:** {status_info.get('index_version', 'unknown')}\n"
        response_text += f"🔨 **Build SHA:** {status_info.get('build_sha', 'unknown')}\n"
        response_text += f"📅 **Built At:** {status_info.get('built_at', 'unknown')}\n"
        response_text += f"🐍 **Python:** {status_info.get('python_version', 'unknown')} ({status_info.get('python_implementation', 'unknown')})\n"
        response_text += f"🌎 **Environment:** {status_info.get('environment', 'unknown')}\n"
        dependencies = status_info.get("dependencies", {})
        if dependencies:
            response_text += "📦 **Dependencies:**\n"
            for dep, ver in dependencies.items():
                response_text += f"  - {dep}: {ver}\n"

        return [types.TextContent(type="text", text=response_text)]

    async def initialize(
        self,
        config_path: Path,
        embeddings_path: Path,
        weights_path: Optional[Path] = None,
    ):
        """Initialize the RAG service."""
        try:
            self.rag_service = RAGService(
                config_path=config_path,
                embeddings_path=embeddings_path,
                weights_path=weights_path,
            )
            print("✅ Nancy Brain MCP Server initialized successfully")
            print(f"📂 Config: {config_path}")
            print(f"🔍 Embeddings: {embeddings_path}")
            if weights_path:
                print(f"⚖️ Weights: {weights_path}")
        except Exception as e:
            print(f"❌ Failed to initialize Nancy Brain: {e}")
            raise

    async def run(self):
        """Run the MCP server."""
        # Using stdio transport (most common for MCP)
        async with stdio_server() as (read_stream, write_stream):
            await self.server.run(
                read_stream,
                write_stream,
                InitializationOptions(
                    server_name="nancy-brain",
                    server_version="1.0.0",
                    capabilities=self.server.get_capabilities(
                        notification_options=NotificationOptions(),
                        experimental_capabilities={},
                    ),
                ),
            )


async def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Nancy Brain MCP Server")
    parser.add_argument("config_path", help="Path to repositories.yml config file")
    parser.add_argument("embeddings_path", help="Path to embeddings directory")
    parser.add_argument("--weights", help="Path to weights.yaml file", default=None)

    args = parser.parse_args()

    config_path = Path(args.config_path)
    embeddings_path = Path(args.embeddings_path)
    weights_path = Path(args.weights) if args.weights else None

    # Validate paths
    if not config_path.exists():
        print(f"❌ Config file not found: {config_path}")
        sys.exit(1)

    if not embeddings_path.exists():
        print(f"❌ Embeddings directory not found: {embeddings_path}")
        sys.exit(1)

    if weights_path and not weights_path.exists():
        print(f"❌ Weights file not found: {weights_path}")
        sys.exit(1)

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
