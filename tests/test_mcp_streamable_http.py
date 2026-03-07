import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest
import requests


ROOT = Path(__file__).resolve().parent.parent
SERVER_PATH = ROOT / "connectors" / "mcp_server" / "server.py"
CONFIG_PATH = ROOT / "config" / "repositories.yml"
EMBEDDINGS_PATH = ROOT / "knowledge_base" / "embeddings"
WEIGHTS_PATH = ROOT / "config" / "index_weights.yaml"


def _free_port() -> int:
    """Return a free TCP port on localhost by binding to port 0."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _wait_for_health(base_url: str, timeout: int = 45) -> bool:
    start = time.time()
    while time.time() - start < timeout:
        try:
            resp = requests.get(f"{base_url}/health", timeout=2)
            if resp.ok:
                return True
        except Exception:
            pass
        time.sleep(1)
    return False


def _start_server(
    port: int,
    config_path: Path,
    embeddings_path: Path,
    weights_path: Path,
) -> subprocess.Popen:
    """Start the MCP HTTP server subprocess and return the process handle."""
    env = os.environ.copy()
    env.update(
        {
            "MCP_CONFIG_PATH": str(config_path),
            "MCP_EMBEDDINGS_PATH": str(embeddings_path),
            "MCP_WEIGHTS_PATH": str(weights_path),
        }
    )

    cmd = [
        sys.executable,
        str(SERVER_PATH),
        "--port",
        str(port),
    ]

    return subprocess.Popen(cmd, env=env)
@pytest.fixture(scope="module")
def mcp_embeddings_fixture(tmp_path_factory):
    """Create a minimal fixture directory tree so the MCP server can start in CI."""
    base = tmp_path_factory.mktemp("mcp_kb")

    # Minimal repositories config (empty registry is fine for protocol/tool-listing tests)
    config_path = base / "repositories.yml"
    config_path.write_text("{}\n")

    # Minimal embeddings directory (no index required just to start the server)
    embeddings_path = base / "embeddings"
    embeddings_path.mkdir()

    # Minimal index_weights.yaml (must not contain model_weights / doc_weights / documents)
    weights_path = base / "index_weights.yaml"
    weights_path.write_text("extensions: {}\npath_includes: {}\n")

    return config_path, embeddings_path, weights_path


@pytest.fixture(scope="module")
def mcp_http_server(mcp_embeddings_fixture):
    config_path, embeddings_path, weights_path = mcp_embeddings_fixture

    env = os.environ.copy()
    env["MCP_PORT"] = str(port)
    env["MCP_API_KEY"] = "test-key"
    return subprocess.Popen(
        [
            sys.executable,
            "-u",
            str(SERVER_PATH),
            str(config_path),
            str(embeddings_path),
            "--weights",
            str(weights_path),
            "--http",
            "--port",
            str(port),
        ],
        cwd=str(ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        env=env,
    )


@pytest.fixture(scope="module")
def mcp_http_server():
    proc = None
    last_out = ""
    for _ in range(3):
        port = _free_port()
        proc = _start_server(port)
        base_url = f"http://127.0.0.1:{port}"
        if _wait_for_health(base_url):
            break
        last_out = ""
        try:
            last_out, _ = proc.communicate(timeout=5)
        except Exception:
            pass
        proc.kill()
        proc = None
    else:
        pytest.fail(f"MCP HTTP server failed to start after retries\n{last_out}")

    try:
        yield base_url
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except Exception:
            proc.kill()


def _parse_sse_json(body: str) -> dict:
    for line in body.splitlines():
        if line.startswith("data: "):
            return json.loads(line[6:])
    raise AssertionError(f"No SSE data payload found in response body: {body[:200]!r}")


def test_mcp_streamable_http_initialize_and_list_tools(mcp_http_server):
    mcp_url = f"{mcp_http_server}/mcp/"
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        "MCP-Protocol-Version": "2025-11-25",
        "X-API-Key": "test-key",
    }
    initialize_req = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-11-25",
            "capabilities": {},
            "clientInfo": {"name": "pytest", "version": "1.0"},
        },
    }

    init_resp = requests.post(mcp_url, headers=headers, json=initialize_req, timeout=30)
    assert init_resp.status_code == 200
    assert "text/event-stream" in init_resp.headers.get("Content-Type", "")
    session_id = init_resp.headers.get("mcp-session-id")
    assert session_id

    init_payload = _parse_sse_json(init_resp.text)
    assert init_payload.get("jsonrpc") == "2.0"
    assert init_payload.get("id") == 1
    assert init_payload.get("result", {}).get("serverInfo", {}).get("name") == "nancy-brain"

    session_headers = headers | {"MCP-Session-Id": session_id}
    notif = {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}}
    notif_resp = requests.post(mcp_url, headers=session_headers, json=notif, timeout=30)
    assert notif_resp.status_code in (200, 202)

    list_tools_req = {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}
    tools_resp = requests.post(mcp_url, headers=session_headers, json=list_tools_req, timeout=30)
    assert tools_resp.status_code == 200
    tools_payload = _parse_sse_json(tools_resp.text)
    tool_names = {tool.get("name") for tool in tools_payload.get("result", {}).get("tools", [])}
    assert "search_knowledge_base" in tool_names
    assert "retrieve_document_passage" in tool_names
    assert "explore_document_tree" in tool_names


def test_mcp_streamable_http_requires_api_key(mcp_http_server):
    mcp_url = f"{mcp_http_server}/mcp/"
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        "MCP-Protocol-Version": "2025-11-25",
    }
    initialize_req = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-11-25",
            "capabilities": {},
            "clientInfo": {"name": "pytest", "version": "1.0"},
        },
    }

    resp = requests.post(mcp_url, headers=headers, json=initialize_req, timeout=30)
    assert resp.status_code == 401
