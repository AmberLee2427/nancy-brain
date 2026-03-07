#!/usr/bin/env python3
"""
Nancy Brain MCP server for search, retrieval, tree listing, and weight updates.
"""

import argparse
import asyncio
import json
import logging
import os
import re
import secrets
import sqlite3
import sys
from contextlib import asynccontextmanager

# Fix OpenMP issue before importing any ML libraries
os.environ["KMP_DUPLICATE_LIB_OK"] = "TRUE"
# Avoid tqdm/progress output errors when running non-interactive inside containers.
os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
os.environ.setdefault("TQDM_DISABLE", "1")

from pathlib import Path
from typing import Any, Dict, List, Optional

from mcp import stdio_server
from mcp import types
from mcp.server import InitializationOptions, NotificationOptions, Server

from nancy_brain.chunking import strip_chunk_suffix
from rag_core.service import RAGService

logger = logging.getLogger(__name__)


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
                                "description": "Starting line number (1-based, inclusive)",
                            },
                            "end": {
                                "type": "integer",
                                "description": "Ending line number (1-based, inclusive)",
                            },
                            "window": {
                                "type": "integer",
                                "description": (
                                    "Number of surrounding chunks to include when " "doc_id is a chunk (default: 1)"
                                ),
                                "default": 1,
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
                            "doc_id": {
                                "type": "string",
                                "description": (
                                    "Optional exact document ID to weight (e.g., "
                                    "'microlensing_tools/MulensModel/README.md')"
                                ),
                            },
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
                        "anyOf": [
                            {"required": ["weight", "doc_id"]},
                            {"required": ["weight", "namespace"]},
                        ],
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

    def _parse_chunk_id(self, doc_id: str):
        """Parse chunk identifiers and return (base, marker, index, width)."""
        if not doc_id:
            return None
        match = re.match(r"^(?P<base>.+?)(?P<marker>(::chunk-|#chunk-|@chunk:|\|chunk:))(?P<idx>\d+)$", doc_id)
        if not match:
            return None
        base = match.group("base")
        marker = match.group("marker")
        idx_str = match.group("idx")
        return base, marker, int(idx_str), len(idx_str)

    def _get_embeddings_db_path(self) -> Optional[Path]:
        if not self.rag_service:
            return None
        try:
            return Path(self.rag_service.embeddings_path) / "index" / "documents"
        except Exception:
            return None

    def _fetch_section_row(self, conn: sqlite3.Connection, doc_id: str) -> Optional[Dict[str, Any]]:
        """Fetch a section row by id and return a dict with text/metadata if available."""
        try:
            columns = [row[1] for row in conn.execute("PRAGMA table_info(sections)").fetchall()]
        except Exception:
            columns = []

        if not columns:
            return None

        select_cols = ["id", "text"]
        if "data" in columns:
            select_cols.append("data")
        if "metadata" in columns and "data" not in columns:
            select_cols.append("metadata")

        query = f"SELECT {', '.join(select_cols)} FROM sections WHERE id = ? LIMIT 1"
        try:
            row = conn.execute(query, (doc_id,)).fetchone()
        except Exception:
            return None
        if not row:
            return None

        result = {"id": row[0], "text": row[1]}
        if len(row) >= 3 and row[2]:
            try:
                meta = json.loads(row[2])
                if isinstance(meta, dict):
                    result["data"] = meta
            except Exception:
                pass
        return result

    def _retrieve_chunk_window(self, doc_id: str, window: int = 1) -> Optional[Dict[str, Any]]:
        parsed = self._parse_chunk_id(doc_id)
        if not parsed:
            return None
        base, marker, idx, width = parsed
        db_path = self._get_embeddings_db_path()
        if not db_path or not db_path.exists():
            return None

        fmt = f"{{:0{width}d}}" if width > 1 else "{}"
        chunk_ids = []
        for i in range(max(0, idx - window), idx + window + 1):
            chunk_ids.append(f"{base}{marker}{fmt.format(i)}")

        chunks = []
        try:
            conn = sqlite3.connect(str(db_path))
        except Exception:
            return None
        try:
            for cid in chunk_ids:
                row = self._fetch_section_row(conn, cid)
                if not row:
                    continue
                data = row.get("data") if isinstance(row.get("data"), dict) else {}
                chunks.append(
                    {
                        "doc_id": row.get("id"),
                        "text": row.get("text", ""),
                        "line_start": data.get("line_start"),
                        "line_end": data.get("line_end"),
                        "chunk_index": data.get("chunk_index"),
                        "chunk_count": data.get("chunk_count"),
                        "source_document": data.get("source_document") or strip_chunk_suffix(row.get("id", "")),
                    }
                )
        finally:
            try:
                conn.close()
            except Exception:
                pass

        if not chunks:
            return None

        combined = []
        for ch in chunks:
            label = ch.get("doc_id") or "chunk"
            combined.append(f"[Chunk] {label}\n{ch.get('text', '')}")
        return {"text": "\n\n".join(combined), "chunks": chunks}

    def _resolve_retrievable_doc_id(self, doc_id: str) -> str:
        """
        Resolve user-facing doc_id aliases to an actual stored section id/path.
        This bridges schema/client drift where search returns one identifier form
        but retrieve expects another.
        """
        if not doc_id:
            return doc_id

        db_path = self._get_embeddings_db_path()
        if not db_path or not db_path.exists():
            return doc_id

        direct_candidates = [doc_id]
        if not self._parse_chunk_id(doc_id):
            direct_candidates.extend(
                [
                    f"{doc_id}::chunk-0",
                    f"{doc_id}#chunk-0",
                    f"{doc_id}|chunk:0",
                ]
            )
        if not doc_id.startswith("knowledge_base/raw/"):
            prefixed = f"knowledge_base/raw/{doc_id}"
            direct_candidates.extend(
                [
                    prefixed,
                    f"{prefixed}::chunk-0",
                    f"{prefixed}#chunk-0",
                    f"{prefixed}|chunk:0",
                ]
            )

        try:
            conn = sqlite3.connect(str(db_path))
        except Exception:
            return doc_id
        try:
            for candidate in direct_candidates:
                row = self._fetch_section_row(conn, candidate)
                if row:
                    return candidate

            # Try lookup by source_document metadata when ids are chunked differently.
            columns = [row[1] for row in conn.execute("PRAGMA table_info(sections)").fetchall()]
            meta_col = "data" if "data" in columns else ("metadata" if "metadata" in columns else None)
            if not meta_col:
                return doc_id

            source_candidates = [doc_id]
            if not doc_id.startswith("knowledge_base/raw/"):
                source_candidates.append(f"knowledge_base/raw/{doc_id}")

            for source_id in source_candidates:
                query = f"""
                    SELECT id
                    FROM sections
                    WHERE json_extract({meta_col}, '$.source_document') = ?
                    ORDER BY
                        COALESCE(json_extract({meta_col}, '$.chunk_index'), 0) ASC,
                        id ASC
                    LIMIT 1
                """
                match = conn.execute(query, (source_id,)).fetchone()
                if match and match[0]:
                    return str(match[0])

            return doc_id
        finally:
            try:
                conn.close()
            except Exception:
                pass

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
        start = args.get("start")
        end = args.get("end")
        window = args.get("window", 1)

        result = None
        total_lines = None
        resolved_doc_id = self._resolve_retrievable_doc_id(doc_id)
        base_doc_id = strip_chunk_suffix(resolved_doc_id)

        # If line range specified, retrieve from the base document (1-based inclusive)
        if start is not None or end is not None:
            start0 = max(int(start) - 1, 0) if start is not None else None
            end0 = int(end) if end is not None else None
            try:
                result = await self.rag_service.retrieve(base_doc_id, start0, end0)
            except FileNotFoundError:
                result = None
            if not result:
                # Some indexed entries are chunk-only; fall back to a chunk window.
                chunk_window = self._retrieve_chunk_window(resolved_doc_id, window=window)
                if chunk_window:
                    logger.error(
                        "Range retrieval fallback to chunk window "
                        "(requested=%s, resolved=%s, start=%s, end=%s, window=%s)",
                        doc_id,
                        resolved_doc_id,
                        start,
                        end,
                        window,
                    )
                    result = {
                        "doc_id": resolved_doc_id,
                        "text": chunk_window.get("text", ""),
                        "chunks": chunk_window.get("chunks", []),
                        "mode": "chunk_window",
                    }
        else:
            # Default: if chunk id, return surrounding chunks
            chunk_window = self._retrieve_chunk_window(resolved_doc_id, window=window)
            if chunk_window:
                result = {
                    "doc_id": resolved_doc_id,
                    "text": chunk_window.get("text", ""),
                    "chunks": chunk_window.get("chunks", []),
                    "mode": "chunk_window",
                }
            else:
                # Fallback: full document
                result = await self.rag_service.retrieve(base_doc_id, None, None)

        if not result:
            return [types.TextContent(type="text", text=f"❌ Document not found: {doc_id}")]

        text = result.get("text", "")
        github_url = result.get("github_url", "") or self.rag_service.registry.get_github_url(base_doc_id)

        # Get total lines in document for file-based retrievals
        if result.get("mode") != "chunk_window":
            try:
                from rag_core.store import Store

                store = Store(self.rag_service.embeddings_path.parent)
                doc_path = store.base_path / base_doc_id
                if not doc_path.exists():
                    doc_path = store.base_path / f"{base_doc_id}.txt"
                if doc_path.exists():
                    with open(doc_path, "r") as f:
                        total_lines = sum(1 for _ in f)
            except Exception:
                total_lines = None

        response_text = f"📄 **Document:** {doc_id}\n"
        if github_url:
            response_text += f"🔗 **GitHub:** {github_url}\n"

        if result.get("mode") == "chunk_window":
            chunks = result.get("chunks", [])
            response_text += f"**Chunks:** {len(chunks)}\n"
            for ch in chunks:
                line_start = ch.get("line_start")
                line_end = ch.get("line_end")
                if line_start and line_end:
                    response_text += f"• {ch.get('doc_id')}: lines {line_start}-{line_end}\n"
                else:
                    response_text += f"• {ch.get('doc_id')}\n"
        else:
            line_start = start if start is not None else 1
            line_end = end if end is not None else "EOF"
            response_text += f"**Lines:** {line_start} - {line_end}"
            if total_lines is not None:
                response_text += f" / {total_lines} total"
            if start is not None or end is not None:
                response_text += "\n⚠️ *Partial passage returned*"

        fence = "```"
        response_text += f"\n\n{fence}\n{text}\n{fence}"

        return [types.TextContent(type="text", text=response_text)]

    async def _handle_retrieve_batch(self, args: Dict[str, Any]) -> list[types.TextContent]:
        """Handle retrieve_multiple_passages tool."""
        items = args["items"]

        results = await self.rag_service.retrieve_batch(items)

        if not results:
            return [types.TextContent(type="text", text="❌ No documents retrieved")]

        response_text = f"📄 **Retrieved {len(results)} passages:**\n\n"

        from rag_core.store import Store

        store = Store(self.rag_service.embeddings_path.parent)
        for i, result in enumerate(results, 1):
            doc_id = result.get("doc_id", "unknown")
            text = result.get("text", "")
            github_url = result.get("github_url", "")
            start = items[i - 1].get("start", 0)
            end = items[i - 1].get("end")
            # Get total lines in document
            try:
                doc_path = store.base_path / doc_id
                if not doc_path.exists():
                    doc_path = store.base_path / f"{doc_id}.txt"
                total_lines = 0
                if doc_path.exists():
                    with open(doc_path, "r") as f:
                        total_lines = sum(1 for _ in f)
            except Exception:
                total_lines = None
            partial = start != 0 or (end is not None and total_lines is not None and end < total_lines)
            response_text += f"**{i}. {doc_id}**\n"
            if github_url:
                response_text += f"🔗 {github_url}\n"
            response_text += f"**Lines:** {start} - {end if end is not None else 'EOF'}"
            if total_lines is not None:
                response_text += f" / {total_lines} total"
            if partial:
                response_text += "\n⚠️ *Partial passage returned*"
            fence = "```"
            response_text += f"\n\n{fence}\n{text}\n{fence}"
            if i < len(results):
                response_text += "\n"
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
                    # Newer list_tree responses are flat path/type entries.
                    if "path" in item and "name" not in item:
                        item_path = str(item.get("path", "")).strip()
                        item_type = item.get("type", "file")
                        is_dir = item_type in ("dir", "directory")
                        if item_path:
                            rel_path = item_path
                            if path and item_path.startswith(path.rstrip("/") + "/"):
                                rel_path = item_path[len(path.rstrip("/") + "/") :]
                            rel_depth = rel_path.count("/")
                            prefix = "  " * rel_depth
                        label = item_path or "unknown"
                        if is_dir:
                            formatted += f"{prefix}📁 {label}/\n"
                        else:
                            formatted += f"{prefix}📄 {label}\n"
                        continue

                    name = item.get("name", item.get("path", "unknown"))
                    if item.get("type") in ("file",):
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

        doc_id = args.get("doc_id") or args.get("path")
        namespace = args.get("namespace")
        weight = args["weight"]
        ttl_days = args.get("ttl_days")

        # Namespace-only requests map to a prefix key (e.g. "microlensing_tools/").
        if not doc_id and namespace:
            doc_id = namespace.rstrip("/") + "/"

        if not doc_id:
            return [
                types.TextContent(
                    type="text",
                    text="❌ set_retrieval_weights requires either doc_id or namespace.",
                )
            ]

        await self.rag_service.set_weight(doc_id, weight, namespace or "global", ttl_days)

        # Show the actual clamped weight
        clamped_weight = max(0.5, min(weight, 2.0))

        response_text = "⚖️ **Weight Updated:**\n"
        target_label = "Namespace Prefix" if namespace and not args.get("doc_id") else "Document"
        response_text += f"{target_label}: `{doc_id}`\n"
        response_text += f"Requested Weight: `{weight}`\n"
        if clamped_weight != weight:
            response_text += f"Actual Weight: `{clamped_weight}` (clamped to safe range 0.5-2.0)\n"
        else:
            response_text += f"Applied Weight: `{weight}`\n"
        response_text += f"Namespace: `{namespace or 'global'}`\n"
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
        response_text += (
            f"🐍 **Python:** {status_info.get('python_version', 'unknown')} "
            f"({status_info.get('python_implementation', 'unknown')})\n"
        )
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
    parser.add_argument(
        "--weights",
        help="Path to index_weights.yaml file (extension/path weights only, NOT model weights)",
        default="config/index_weights.yaml",
    )
    parser.add_argument(
        "--http",
        help="Run Nancy Brain MCP server in HTTP mode (for Custom GPT connections)",
        action="store_true",
    )
    parser.add_argument(
        "--http-and-stdio",
        help="Run Nancy Brain MCP server in BOTH HTTP and stdio modes (for testing both interfaces)",
        action="store_true",
    )
    parser.add_argument(
        "--port",
        help="HTTP port to listen on (default: 8000)",
        type=int,
        default=8000,
    )

    args = parser.parse_args()

    config_path = Path(args.config_path)
    embeddings_path = Path(args.embeddings_path)
    weights_path = Path(args.weights) if args.weights else Path("config/index_weights.yaml")
    port = args.port

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

    # Validate that the weights file is NOT a model weights file (should not contain per-document weights)
    import yaml

    try:
        with open(weights_path, "r") as f:
            data = yaml.safe_load(f) or {}
            forbidden_keys = {"model_weights", "doc_weights", "documents"}
            if any(k in data for k in forbidden_keys):
                print(
                    f"❌ ERROR: The weights file '{weights_path}' appears to be a model "
                    f"weights file (contains {forbidden_keys}). Please provide an "
                    "index_weights.yaml file for extension/path weights only."
                )
                sys.exit(1)
    except Exception as e:
        print(f"❌ Failed to validate weights file: {e}")
        sys.exit(1)

    # Create and run server
    server = NancyMCPServer()

    try:
        await server.initialize(config_path, embeddings_path, weights_path)

        def build_http_app():
            from fastapi import FastAPI, Request, HTTPException, Header, Depends
            from fastapi.security import OAuth2PasswordRequestForm
            from mcp.server.fastmcp.server import StreamableHTTPASGIApp
            from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
            from starlette.responses import JSONResponse
            from typing import Optional
            from connectors.http_api import auth

            # Initialize user tables
            auth.create_user_table()
            auth.create_refresh_table()
            auth.create_api_key_table()

            streamable_http_manager = StreamableHTTPSessionManager(app=server.server, stateless=False)
            streamable_http_app = StreamableHTTPASGIApp(streamable_http_manager)

            def _is_valid_api_key(value: Optional[str]) -> bool:
                expected_key = os.environ.get("MCP_API_KEY")
                if value:
                    if expected_key and secrets.compare_digest(value, expected_key):
                        return True
                    if auth.is_api_key_valid(value):
                        return True
                return False

            class MCPAuthApp:
                async def __call__(self, scope, receive, send):
                    headers = {
                        key.decode("latin1").lower(): value.decode("latin1")
                        for key, value in scope.get("headers", [])
                    }
                    x_api_key = headers.get("x-api-key")
                    auth_header = headers.get("authorization", "")
                    bearer = auth_header[7:].strip() if auth_header.lower().startswith("bearer ") else None

                    provided = x_api_key or bearer
                    if not _is_valid_api_key(provided):
                        expected_key = os.environ.get("MCP_API_KEY")
                        if expected_key or auth.any_api_keys_exist():
                            response = JSONResponse({"detail": "Invalid or missing API key"}, status_code=401)
                            await response(scope, receive, send)
                            return
                    await streamable_http_app(scope, receive, send)

            @asynccontextmanager
            async def lifespan(_app):
                async with streamable_http_manager.run():
                    yield

            app = FastAPI(lifespan=lifespan)
            app.mount("/mcp", MCPAuthApp())

            # --- Authentication Endpoints ---
            @app.post("/login")
            def login(form_data: OAuth2PasswordRequestForm = Depends()):
                user = auth.authenticate_user(form_data.username, form_data.password)
                if not user:
                    raise HTTPException(status_code=400, detail="Incorrect username or password")
                access_token = auth.create_access_token(data={"sub": user["username"]})
                refresh_token = auth.create_refresh_token(data={"sub": user["username"]})
                try:
                    auth.store_refresh_token(user["username"], refresh_token)
                except Exception:
                    pass
                return {"access_token": access_token, "refresh_token": refresh_token, "token_type": "bearer"}

            @app.post("/refresh")
            def refresh_token_endpoint(payload: dict):
                token = payload.get("refresh_token")
                username = auth.verify_token(token)
                if not username:
                    raise HTTPException(status_code=401, detail="Invalid refresh token")
                if not auth.is_refresh_valid(token):
                    raise HTTPException(status_code=401, detail="Refresh token revoked or unknown")
                new_access = auth.create_access_token(data={"sub": username})
                return {"access_token": new_access, "token_type": "bearer"}

            # --------------------------------

            def _get_invite_codes() -> List[str]:
                raw = os.environ.get("MCP_INVITE_CODES", "")
                return [code.strip() for code in raw.split(",") if code.strip()]

            def _invite_code_valid(code: str, allowed: List[str]) -> bool:
                return any(secrets.compare_digest(code, candidate) for candidate in allowed)

            def _require_admin_api_key(x_api_key: Optional[str] = Header(None)) -> str:
                expected_key = os.environ.get("MCP_API_KEY")
                if not expected_key:
                    raise HTTPException(status_code=503, detail="MCP_API_KEY not configured")
                if not x_api_key or not secrets.compare_digest(x_api_key, expected_key):
                    raise HTTPException(status_code=401, detail="Invalid API key")
                return x_api_key

            @app.post("/v2/api-keys/request")
            async def issue_api_key(request: Request):
                data = await request.json()
                invite_code = (data.get("invite_code") or "").strip()
                contact = data.get("contact")
                label = data.get("label")

                if not invite_code:
                    raise HTTPException(status_code=400, detail="invite_code is required")

                allowed = _get_invite_codes()
                if not allowed:
                    raise HTTPException(status_code=503, detail="Invite codes not configured")

                if not _invite_code_valid(invite_code, allowed):
                    raise HTTPException(status_code=401, detail="Invalid invite code")

                api_key = auth.issue_api_key(contact=contact, label=label)
                return {"api_key": api_key, "token_type": "api_key"}

            @app.post("/v2/api-keys/issue")
            async def issue_api_key_admin(request: Request, _admin_key: str = Depends(_require_admin_api_key)):
                data = await request.json()
                contact = data.get("contact")
                label = data.get("label")
                api_key = auth.issue_api_key(contact=contact, label=label)
                return {"api_key": api_key, "token_type": "api_key"}

            # Simple API key authentication
            def verify_api_key(x_api_key: Optional[str] = Header(None)):
                expected_key = os.environ.get("MCP_API_KEY")
                if x_api_key:
                    if expected_key and secrets.compare_digest(x_api_key, expected_key):
                        return x_api_key
                    if auth.is_api_key_valid(x_api_key):
                        return x_api_key
                    raise HTTPException(status_code=401, detail="Invalid API key")
                if expected_key or auth.any_api_keys_exist():
                    raise HTTPException(status_code=401, detail="Missing API key")
                return x_api_key

            @app.get("/health")
            async def health():
                if hasattr(server.rag_service, "system_status"):
                    status = await server.rag_service.system_status()
                else:
                    status = {"status": "ok"}
                return status

            @app.get("/search")
            async def search(query: str = "", limit: int = 5, api_key: str = Depends(verify_api_key)):
                def _to_json_safe(value):
                    if isinstance(value, dict):
                        return {k: _to_json_safe(v) for k, v in value.items()}
                    if isinstance(value, list):
                        return [_to_json_safe(v) for v in value]
                    if hasattr(value, "item") and callable(getattr(value, "item", None)):
                        try:
                            return value.item()
                        except Exception:
                            return value
                    return value

                results = await server.rag_service.search_docs(query=query, limit=limit)
                # Promote common chunk metadata fields to top-level for convenience
                for r in results:
                    data = r.get("data") if isinstance(r.get("data"), dict) else {}
                    if data:
                        for key in ("line_start", "line_end", "chunk_index", "chunk_count", "source_document"):
                            if key in data and key not in r:
                                r[key] = data[key]
                return {"hits": _to_json_safe(results)}

            @app.get("/tree")
            async def tree(
                prefix: str = "",
                depth: int = 2,
                max_entries: int = 500,
                api_key: str = Depends(verify_api_key),
            ):
                # Compatibility endpoint for older GPT action schemas.
                entries = await server.rag_service.list_tree(prefix=prefix, depth=depth, max_entries=max_entries)
                normalized = []
                for entry in entries:
                    entry_type = entry.get("type", "file")
                    if entry_type == "directory":
                        entry_type = "dir"
                    normalized.append({"path": entry.get("path", ""), "type": entry_type})
                return {"entries": normalized}

            @app.post("/retrieve")
            async def retrieve(request: Request, api_key: str = Depends(verify_api_key)):
                data = await request.json()
                doc_id = data.get("doc_id") or data.get("file_path") or data.get("path")
                start = data.get("start")
                end = data.get("end")
                window = data.get("window", 1)
                if not doc_id:
                    raise HTTPException(status_code=400, detail="doc_id, file_path, or path is required")
                try:
                    resolved_doc_id = server._resolve_retrievable_doc_id(str(doc_id))
                    base_doc_id = strip_chunk_suffix(resolved_doc_id)
                    result = None
                    if start is not None or end is not None:
                        start0 = max(int(start) - 1, 0) if start is not None else None
                        end0 = int(end) if end is not None else None
                        try:
                            result = await server.rag_service.retrieve(base_doc_id, start0, end0)
                        except FileNotFoundError:
                            result = None
                        if not result:
                            chunk_window = server._retrieve_chunk_window(resolved_doc_id, window=window)
                            if chunk_window:
                                logger.error(
                                    "HTTP range retrieval fallback to chunk window "
                                    "(requested=%s, resolved=%s, start=%s, end=%s, window=%s)",
                                    doc_id,
                                    resolved_doc_id,
                                    start,
                                    end,
                                    window,
                                )
                                result = {
                                    "doc_id": resolved_doc_id,
                                    "text": chunk_window.get("text", ""),
                                    "chunks": chunk_window.get("chunks", []),
                                    "mode": "chunk_window",
                                }
                        if result is not None:
                            result["start"] = start
                            result["end"] = end
                    else:
                        chunk_window = server._retrieve_chunk_window(resolved_doc_id, window=window)
                        if chunk_window:
                            result = {
                                "doc_id": resolved_doc_id,
                                "text": chunk_window.get("text", ""),
                                "chunks": chunk_window.get("chunks", []),
                                "mode": "chunk_window",
                            }
                        else:
                            result = await server.rag_service.retrieve(base_doc_id, None, None)

                    # Attach github_url and total_lines when possible
                    if result is not None and result.get("mode") != "chunk_window":
                        result.setdefault("doc_id", base_doc_id)
                        result.setdefault("github_url", server.rag_service.registry.get_github_url(base_doc_id) or "")
                        try:
                            from rag_core.store import Store

                            store = Store(server.rag_service.embeddings_path.parent)
                            doc_path = store.base_path / base_doc_id
                            if not doc_path.exists():
                                doc_path = store.base_path / f"{base_doc_id}.txt"
                            if doc_path.exists():
                                with open(doc_path, "r") as f:
                                    result["total_lines"] = sum(1 for _ in f)
                        except Exception:
                            pass

                    return {"passage": result}
                except FileNotFoundError:
                    from fastapi.responses import JSONResponse

                    return JSONResponse({"error": f"Document not found: {doc_id}"}, status_code=404)
                except Exception as exc:
                    from fastapi.responses import JSONResponse

                    return JSONResponse({"error": str(exc)}, status_code=500)

            @app.post("/weight")
            async def weight(request: Request, api_key: str = Depends(verify_api_key)):
                # Compatibility endpoint for older GPT action schemas.
                data = await request.json()
                doc_id = data.get("doc_id") or data.get("path")
                if not doc_id:
                    raise HTTPException(status_code=400, detail="doc_id or path is required")
                multiplier = float(data.get("multiplier", 1.0))
                namespace = data.get("namespace", "global")
                ttl_days = data.get("ttl_days")
                await server.rag_service.set_weight(
                    doc_id=str(doc_id),
                    multiplier=multiplier,
                    namespace=str(namespace),
                    ttl_days=ttl_days,
                )
                return {"status": "success", "doc_id": str(doc_id), "multiplier": multiplier}

            @app.post("/embeddings/sql")
            async def embeddings_sql(request: Request, api_key: str = Depends(verify_api_key)):
                data = await request.json()
                sql = data.get("sql", "")
                # Reuse search_docs as a lightweight fallback for SQL-like queries
                try:
                    rows = await server.rag_service.search_docs(query=sql, limit=500)
                except Exception:
                    rows = []
                return {"rows": rows}

            @app.get("/doc/{doc_id}/url")
            async def doc_url(doc_id: str, api_key: str = Depends(verify_api_key)):
                meta = server.rag_service.registry.get_meta(doc_id)
                return {"github_url": meta.github_url}

            @app.post("/rebuild")
            async def rebuild_embeddings(request: Request, api_key: str = Depends(verify_api_key)):
                """Trigger a rebuild of the embeddings index"""
                import subprocess

                try:
                    # Run the build script in the background
                    subprocess.Popen(
                        [
                            sys.executable,
                            "-m",
                            "nancy_brain.cli",
                            "build",
                            str(config_path),
                            str(embeddings_path.parent),
                        ]
                    )
                    return {"status": "rebuild_triggered", "message": "Embedding rebuild started in background"}
                except Exception as e:
                    raise HTTPException(status_code=500, detail=f"Failed to trigger rebuild: {str(e)}")

            return app

        if args.http_and_stdio:
            # Run BOTH HTTP and stdio servers concurrently inside this event loop.
            import uvicorn

            app = build_http_app()

            print(f"🌐 Nancy Brain MCP Server running in HTTP mode on port {port}")
            print("🔗 Nancy Brain MCP Server also running in stdio mode")

            config = uvicorn.Config(app, host="0.0.0.0", port=port, loop="asyncio")
            http_server = uvicorn.Server(config)

            http_task = asyncio.create_task(http_server.serve())
            stdio_task = asyncio.create_task(server.run())

            await asyncio.gather(http_task, stdio_task)
        elif args.http:
            # HTTP mode only
            import uvicorn

            app = build_http_app()

            print(f"🌐 Nancy Brain MCP Server running in HTTP mode on port {port}")

            config = uvicorn.Config(app, host="0.0.0.0", port=port, loop="asyncio")
            http_server = uvicorn.Server(config)
            await http_server.serve()
        else:
            # Default: stdio mode (secure, recommended for bot)
            await server.run()
    except KeyboardInterrupt:
        print("\n👋 Nancy Brain MCP Server shutting down...")
    except Exception as e:
        print(f"❌ Server error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
