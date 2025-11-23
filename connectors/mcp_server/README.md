# Nancy Brain MCP Server: Passage Retrieval Tool Schemas

## Passage Retrieval Tools

### `retrieve_document_passage`
- **Description:** Retrieve a specific passage from a document by ID and line range.
- **Input Schema:**
  - `doc_id` (string): Document ID (e.g., 'microlensing_tools/MulensModel/README.md')
  - `start` (integer, default 0): Starting line number (0-based)
  - `end` (integer): Ending line number (exclusive)
- **Output:**
  - Always includes `doc_id`, `start`, `end`, `text`, and `github_url` (if available).
  - If a partial passage is returned, the response must clearly indicate the line range and total lines in the document.

### `retrieve_multiple_passages`
- **Description:** Retrieve multiple document passages in a single request.
- **Input Schema:**
  - `items` (array): List of objects, each with `doc_id`, `start`, and `end`.
- **Output:**
  - Each result includes `doc_id`, `start`, `end`, `text`, and `github_url`.
  - Partial results are always explicit about line ranges.

## Handler Response Format
- All passage retrieval responses must:
  - Indicate the line range (`start`, `end`) for each passage.
  - Include the total number of lines in the document if possible.
  - Clearly mark when a partial passage is returned (not the full document).
  - Include `github_url` for source traceability.

## Example Response
```json
{
  "doc_id": "microlensing_tools/MulensModel/README.md",
  "start": 10,
  "end": 30,
  "text": "...lines 10-29...",
  "github_url": "https://github.com/.../blob/master/MulensModel/README.md",
  "total_lines": 120
}
```

## Notes
- All tool schemas and handler responses must be updated to reflect these requirements.
- Document this format for all MCP-compatible clients and bot integrations.
