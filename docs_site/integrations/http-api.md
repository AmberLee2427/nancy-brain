# HTTP API Reference

Nancy Brain provides a REST API for programmatic access to the knowledge base.

## Quick Start

Start the HTTP API server:

```bash
python -m nancy_brain.connectors.http_api --port 8000
```

The API will be available at `http://localhost:8000`.

## API Endpoints

### Search Documents

**GET** `/search`

Search the knowledge base for relevant documents.

```bash
curl "http://localhost:8000/search?query=machine%20learning%20algorithms&limit=5&threshold=0.7"
```

**Parameters:**
- `query` (string, required): Search query
- `limit` (integer, optional): Maximum results to return (default: 6)
- `threshold` (number, optional): Minimum relevance score (default: 0.0)
- `toolkit` (string, optional): Filter by toolkit name
- `doctype` (string, optional): Filter by document type

**Response:**
```json
{
  "hits": [
    {
      "id": "repo/path/to/file.py::chunk-0003",
      "text": "relevant content...",
      "score": 0.85,
      "source_document": "repo/path/to/file.py",
      "line_start": 121,
      "line_end": 240,
      "chunk_index": 2,
      "chunk_count": 9
    }
  ],
  "index_version": "1.0.0",
  "trace_id": "trace-123"
}
```

### Retrieve Document

**POST** `/retrieve`

Retrieve a specific document passage.

```bash
curl -X POST http://localhost:8000/retrieve \
  -H "Content-Type: application/json" \
  -d '{
    "doc_id": "repo/path/to/file.py",
    "start": 10,
    "end": 20
  }'
```

**Parameters:**
- `doc_id` (string, required): Document identifier
- `start` (integer, optional): Starting line number (1-based, inclusive)
- `end` (integer, optional): Ending line number (1-based, inclusive)
- `window` (integer, optional): Chunk window size when `doc_id` is a chunk (default: 1)

**Response:**
```json
{
  "passage": {
    "doc_id": "repo/path/to/file.py",
    "text": "document content...",
    "github_url": "https://github.com/user/repo/blob/main/path/to/file.py",
    "content_sha256": "abcdef123456",
    "start": 10,
    "end": 20,
    "total_lines": 420
  },
  "trace_id": "trace-123"
}
```

**Chunk-window example (no line range):**
```bash
curl -X POST http://localhost:8000/retrieve \
  -H "Content-Type: application/json" \
  -d '{
    "doc_id": "repo/path/to/file.py::chunk-0003",
    "window": 1
  }'
```

### Batch Retrieve

**POST** `/retrieve/batch`

Retrieve multiple document passages in one request.

```bash
curl -X POST http://localhost:8000/retrieve/batch \
  -H "Content-Type: application/json" \
  -d '{
    "items": [
      {"doc_id": "repo/file1.py", "start": 1, "end": 10},
      {"doc_id": "repo/file2.py", "start": 5, "end": 15}
    ]
  }'
```

### List Documents

**GET** `/tree`

Get a hierarchical list of all documents in the knowledge base.

```bash
curl "http://localhost:8000/tree?depth=3&prefix=microlensing_tools"
```

**Parameters:**
- `depth` (integer, optional): Maximum tree depth (default: 3)
- `prefix` (string, optional): Filter by path prefix

### Health Check

**GET** `/health`

Check the health and status of the system.

```bash
curl http://localhost:8000/health
```

**Response:**
```json
{
  "status": "ok",
  "index_version": "1.0.0",
  "documents_count": 1234,
  "last_updated": "2025-08-24T12:00:00Z"
}
```

## Authentication

The HTTP API uses bearer authentication. Provide `Authorization: Bearer <token>` for protected endpoints. For development, you can set `NB_ALLOW_INSECURE=true`.

## Rate Limiting

The API includes basic rate limiting to prevent abuse. Default limits:
- 100 requests per minute per IP
- 1000 requests per hour per IP

## Error Handling

The API returns standard HTTP status codes:

- `200` - Success
- `400` - Bad Request (invalid parameters)
- `404` - Not Found (document doesn't exist)
- `429` - Too Many Requests (rate limited)
- `500` - Internal Server Error

Error responses include details:

```json
{
  "error": "Document not found",
  "code": "DOCUMENT_NOT_FOUND",
  "details": "No document with id 'invalid/path.py' exists in the knowledge base"
}
```

## Client Examples

### Python

```python
import requests

# Search for documents
response = requests.get("http://localhost:8000/search", params={
  "query": "neural networks",
  "limit": 5
})
results = response.json()["hits"]

# Retrieve a specific document
doc_id = results[0]["id"]
response = requests.post("http://localhost:8000/retrieve", json={
  "doc_id": doc_id,
  "start": 1,
  "end": 40
})
document = response.json()
```

### JavaScript

```javascript
// Search for documents
const searchResponse = await fetch('http://localhost:8000/search?query=machine%20learning&limit=5');
const results = await searchResponse.json();

// Retrieve a document
const docId = results.hits[0].id;
const docResponse = await fetch('http://localhost:8000/retrieve', {
  method: 'POST',
  headers: {'Content-Type': 'application/json'},
  body: JSON.stringify({
    doc_id: docId,
    start: 1,
    end: 40
  })
});
const document = await docResponse.json();
```

## Configuration

The HTTP API server can be configured via environment variables:

- `NANCY_BRAIN_HOST` - Server host (default: "localhost")
- `NANCY_BRAIN_PORT` - Server port (default: 8000)
- `NANCY_BRAIN_EMBEDDINGS_PATH` - Path to embeddings directory
- `NANCY_BRAIN_CONFIG_PATH` - Path to repositories configuration
- `NANCY_BRAIN_WEIGHTS_PATH` - Path to weights configuration

## Deployment

For production deployment, consider:

1. **Reverse Proxy** - Use nginx or similar
2. **HTTPS** - Enable SSL/TLS encryption
3. **Authentication** - Add API key or OAuth
4. **Monitoring** - Log requests and performance
5. **Scaling** - Use multiple instances behind a load balancer
