from pathlib import Path
import re

import yaml

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = ROOT / "connectors" / "http_api" / "GPT_schema.yml"
MCP_SERVER_PATH = ROOT / "connectors" / "mcp_server" / "server.py"


def _schema_routes(schema_path: Path) -> set[tuple[str, str]]:
    data = yaml.safe_load(schema_path.read_text(encoding="utf-8")) or {}
    paths = data.get("paths", {})
    routes: set[tuple[str, str]] = set()
    for path, methods in paths.items():
        if not isinstance(methods, dict):
            continue
        for method in methods:
            method_lower = str(method).lower()
            if method_lower in {"get", "post", "put", "delete", "patch", "options", "head"}:
                routes.add((method_lower, str(path)))
    return routes


def _mcp_http_routes(server_path: Path) -> set[tuple[str, str]]:
    text = server_path.read_text(encoding="utf-8")
    pattern = re.compile(r'@app\.(get|post|put|delete|patch|options|head)\("([^"]+)"\)')
    return {(method.lower(), path) for method, path in pattern.findall(text)}


def test_gpt_schema_routes_exist_in_mcp_http_server():
    """
    Every path+method published to GPT actions must exist on the MCP HTTP server.
    """
    schema_routes = _schema_routes(SCHEMA_PATH)
    mcp_routes = _mcp_http_routes(MCP_SERVER_PATH)
    missing = sorted(schema_routes - mcp_routes)
    assert not missing, f"Routes in GPT_schema.yml missing from MCP HTTP server: {missing}"
