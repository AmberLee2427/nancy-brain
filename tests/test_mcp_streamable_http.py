import hashlib
import json
import os
import sqlite3
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest
import requests

ROOT = Path(__file__).resolve().parent.parent
SERVER_PATH = ROOT / "connectors" / "mcp_server" / "server.py"


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
    users_db: Path,
) -> subprocess.Popen:
    """Start the MCP HTTP server subprocess and return the process handle."""
    env = os.environ.copy()
    env["MCP_API_KEY"] = "test-key"
    env["MCP_INVITE_CODES"] = "test-invite"
    env["NB_USERS_DB"] = str(users_db)
    env["MCP_PORT"] = str(port)
    env["PYTHONPATH"] = os.pathsep.join(value for value in (str(ROOT), env.get("PYTHONPATH")) if value)
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
    users_db = config_path.parent / "users.db"
    proc = None
    last_out = ""
    base_url = ""
    for _ in range(3):
        port = _free_port()
        proc = _start_server(port, config_path, embeddings_path, weights_path, users_db)
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
        yield {"base_url": base_url, "users_db": users_db}
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
    mcp_url = f"{mcp_http_server['base_url']}/mcp/"
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
    mcp_url = f"{mcp_http_server['base_url']}/mcp/"
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


def test_personal_key_weights_are_scoped_through_mcp_and_cannot_rebuild(mcp_http_server):
    base_url = mcp_http_server["base_url"]
    issued = requests.post(
        f"{base_url}/v2/api-keys/request",
        json={"invite_code": "test-invite", "contact": "user@example.com"},
        timeout=10,
    )
    assert issued.status_code == 200
    personal_key = issued.json()["api_key"]

    rebuild = requests.post(
        f"{base_url}/rebuild",
        headers={"X-API-Key": personal_key},
        json={},
        timeout=10,
    )
    assert rebuild.status_code == 401

    mcp_url = f"{base_url}/mcp/"
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        "MCP-Protocol-Version": "2025-11-25",
        "X-API-Key": personal_key,
    }
    initialize_req = {
        "jsonrpc": "2.0",
        "id": 10,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-11-25",
            "capabilities": {},
            "clientInfo": {"name": "pytest-personal", "version": "1.0"},
        },
    }
    init_resp = requests.post(mcp_url, headers=headers, json=initialize_req, timeout=30)
    assert init_resp.status_code == 200
    session_headers = headers | {"MCP-Session-Id": init_resp.headers["mcp-session-id"]}

    notif = {"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}}
    assert requests.post(mcp_url, headers=session_headers, json=notif, timeout=30).status_code in (200, 202)

    weight_req = {
        "jsonrpc": "2.0",
        "id": 11,
        "method": "tools/call",
        "params": {
            "name": "set_retrieval_weights",
            "arguments": {"doc_id": "docs/private.md", "weight": 1.7},
        },
    }
    weight_resp = requests.post(mcp_url, headers=session_headers, json=weight_req, timeout=30)
    assert weight_resp.status_code == 200
    payload = _parse_sse_json(weight_resp.text)
    assert payload["result"]["isError"] is False
    assert "Personal API key" in payload["result"]["content"][0]["text"]

    principal = hashlib.sha256(personal_key.encode("utf-8")).hexdigest()
    with sqlite3.connect(mcp_http_server["users_db"]) as conn:
        row = conn.execute(
            """
            SELECT multiplier
            FROM api_key_weights
            WHERE principal_id = ? AND doc_id = ?
            """,
            (principal, "docs/private.md"),
        ).fetchone()
    assert row == (1.7,)
