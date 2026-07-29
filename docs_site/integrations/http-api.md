# HTTP API

Nancy Brain's HTTP transport exposes both MCP and direct HTTP endpoints.

## Start the server

```bash
export MCP_TRANSPORT=http
export MCP_PORT=8000
export MCP_API_KEY="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')"
python connectors/mcp_server/server.py \
  config/repositories.yml \
  knowledge_base/embeddings \
  --weights config/index_weights.yaml \
  --http \
  --port 8000
```

Use `0.0.0.0` only inside a controlled container or network. Put TLS and an
access-control layer in front of any internet-facing deployment.

## Authentication

Protected endpoints accept either:

```text
X-API-Key: YOUR_KEY
```

or:

```text
Authorization: Bearer YOUR_KEY
```

Do not set `NB_ALLOW_INSECURE=true` outside isolated development and tests.

## MCP endpoint

MCP clients connect using Streamable HTTP:

```text
http://127.0.0.1:8000/mcp
```

The MCP endpoint requires a valid API key when keys are configured.

## Search

```bash
curl -G http://127.0.0.1:8000/search \
  -H "X-API-Key: ${MCP_API_KEY}" \
  --data-urlencode "query=binary lens modeling" \
  --data-urlencode "limit=5"
```

## Retrieve

```bash
curl -X POST http://127.0.0.1:8000/retrieve \
  -H "X-API-Key: ${MCP_API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{"doc_id":"DOCUMENT_ID","start":1,"end":100}'
```

## Tree

```bash
curl -G http://127.0.0.1:8000/tree \
  -H "X-API-Key: ${MCP_API_KEY}" \
  --data-urlencode "prefix=microlensing_tools" \
  --data-urlencode "depth=3"
```

## Health

```bash
curl http://127.0.0.1:8000/health
```

Health is intentionally unauthenticated for container and load-balancer probes.
Administrative rebuild and SQL endpoints must not be exposed to untrusted
users merely because the read API is public.

## Hosted microlensing API

The shared service has separate access and privacy documentation at
[nancy.rges-pit.com](https://nancy.rges-pit.com/). Package examples here do not
grant access to that deployment.
