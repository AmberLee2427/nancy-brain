# Semantic Chunking Library Design

## 1. Background & Motivation

Our existing `SmartChunker` performs a hybrid of sliding windows and heuristic boundary searches. When processing medium-sized code files the forward/backward scans can explode in CPU and memory, causing build failures. We also have no semantic awareness for other file types, leading to arbitrary splits. To make the knowledge-base pipeline reliable and extensible we want a modular chunking library that:

- Handles our common file types (Python, Markdown, JSON/YAML, plain text) with sensible defaults.
- Lets us plug in stronger semantic strategies (AST, embeddings) as optional enhancements.
- Keeps configuration centralized and easy to override via environment variables or config files.
- Produces consistent `Chunk` objects that slot directly into the indexing pipeline.

## 2. Goals & Non-Goals

### Goals
- Deterministic chunking for code and docs without pathological loops.
- Environment-driven configuration (e.g., tweak window sizes per build).
- Pipeline orchestration that picks the right chunker based on file metadata.
- Clear surface for future semantic/AST-based chunkers.

### Non-Goals
- Building a full AST parser for every language on day one.
- Re-implementing vector stores or summarization; we only prepare text for indexing/summarizing.
- Handling binary formats such as PDFs (they stay outside this module).

## 3. High-Level Architecture

```
semantic_chunks/
├── types.py           # Chunk, Document, ChunkerConfig definitions
├── core.py            # Chunker protocol, ChunkingError
├── chunkers/
│   ├── python.py      # PythonSemanticChunker (AST-aware)
│   ├── markdown.py    # MarkdownHeadingChunker
│   ├── yaml_json.py   # JSONYamlChunker
│   ├── text.py        # PlainTextChunker
│   └── fallback.py    # SlidingWindowChunker
├── registry.py        # ChunkerRegistry + DEFAULT_REGISTRY
├── loaders.py         # DocumentLoader hierarchy
├── pipeline.py        # ChunkPipeline orchestrator
└── utils.py           # Shared helpers (token counting, environment hooks)
```

## 4. Core Concepts

- **Document**: normalized representation of a file with (path, content, metadata, language).
- **Chunk**: dataclass with `chunk_id`, `text`, `metadata` (JSON-serializable), `source_document`.
- **Chunker**: object exposing `chunk(document, config) -> List[Chunk]`.
- **ChunkerRegistry**: resolves the appropriate chunker for a document (by extension, language, or explicit override).
- **ChunkPipeline**: orchestrates loading, chunking, and optional summarization hooks.

## 5. Chunker Implementations

Minimum viable set:

| Chunker | Description | Notes |
|---------|-------------|-------|
| `SlidingWindowChunker` | Simple fixed-line window with overlap | Always available; zero dependencies |
| `PythonSemanticChunker` | AST-based splitting on top-level functions/classes; falls back to window | Requires `ast` (built-in). Optionally `tree_sitter` later |
| `MarkdownHeadingChunker` | Breaks on heading hierarchy; merges small sections | No heavy deps |
| `JSONYamlChunker` | Treats top-level keys/arrays as chunks; flatten nested objects | Uses `json` / `yaml` |
| `PlainTextChunker` | Sentence/paragraph segmentation using regex or spaCy optional | Configurable sentence splitter |
| `SemanticEmbeddingChunker` (optional) | Embedding-based breakpoints (cosine drift) | Depends on configured embedding model; opt-in |

Each chunker adheres to the `Chunker` protocol and accepts a `ChunkerConfig`. The fallback chunker is always used last to guarantee progress.

## 6. Configuration Strategy

- `ChunkerConfig` stores generic knobs (`max_chars`, `max_tokens`, `code_window_lines`, `code_overlap_lines`, `semantic_model`, etc.).
- Defaults come from environment variables (`SMART_CHUNK_CODE_LINES`, `SMART_CHUNK_CODE_OVERLAP`, `SMART_CHUNK_TEXT_CHARS`, `SEMANTIC_MODEL`) or a YAML file (`semantic_chunker.yaml`).
- The pipeline allows per-call overrides, e.g., `pipeline.chunk_file(path, config=ChunkerConfig(code_window_lines=60))`.

## 7. API Sketch

```python
from semantic_chunks.pipeline import ChunkPipeline
from semantic_chunks.types import ChunkerConfig

pipeline = ChunkPipeline()  # uses DEFAULT_REGISTRY

chunks = pipeline.chunk_file(
    path="knowledge_base/raw/general_tools/Dazzle/dazzle/dazzle.py",
    config=ChunkerConfig(
        code_window_lines=80,
        code_overlap_lines=10,
        semantic_model=None,  # disable embedding-based splits
    ),
)

for chunk in chunks:
    print(chunk.chunk_id, chunk.metadata["line_start"], chunk.metadata["line_end"])
```

Pipeline steps internally:
1. Load `Document` via registered loader.
2. Resolve chunker from registry (falls back to sliding window).
3. Invoke chunker with provided config.
4. Optionally post-process (e.g., summarization hook, metadata enrichment).
5. Return list of `Chunk` objects ready for indexing.

## 8. Integration with KB Build

- Replace direct `SmartChunker` usage in `scripts/build_knowledge_base.py` with `ChunkPipeline`.
- All metadata stays JSON-serializable; pipeline returns chunks with ready metadata.
- Existing environment flags (`SKIP_PDF_PROCESSING`, `NB_PER_FILE_LOG`) remain untouched.

## 9. Extensibility Hooks

- `ChunkerRegistry.register(ext, chunker_cls)` to add new chunkers (e.g., notebook support).
- `ChunkPipeline` accepts custom registry or pre/post hooks (e.g., run summarizer on each chunk).
- Optional plugin entry points for projects to register chunkers via setuptools entry points.

## 10. Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| AST parser errors on malformed code | Catch exceptions, fall back to sliding window |
| Semantic chunker slows builds | Make embedding-driven chunker opt-in; default to cheapest strategy |
| Dependency bloat | Keep base package pure-Python. Optional chunkers gated behind extras (`semantic_chunks[semantic]`) |
| Inconsistent metadata | Centralize metadata construction utilities; reuse JSON serialization helpers |

## 11. Implementation Plan

1. **Phase 1 – Infrastructure**
   - Define `Chunk`, `Document`, `ChunkerConfig`.
   - Implement `SlidingWindowChunker` and registry/pipeline scaffold.
   - Swap KB build to use pipeline with sliding window (parity with current behavior).

2. **Phase 2 – Language-specific chunkers**
   - Implement `PythonSemanticChunker`, `MarkdownHeadingChunker`, `JSONYamlChunker`, `PlainTextChunker`.
   - Add tests covering line ranges, metadata, and fallback behavior.

3. **Phase 3 – Semantic chunking (optional)**
   - Prototype embedding-based chunker using existing sentence-transformer models.
   - Benchmark build impact; keep behind feature flag.

4. **Phase 4 – Documentation & Adoption**
   - Document env vars/config file usage.
   - Update KB pipeline guide in README/docs.
   - Gather feedback, iterate on defaults.

## 12. Testing Strategy

- Unit tests per chunker verifying chunk counts, metadata integrity, and fallback logic.
- Golden-file tests comparing chunk outputs for representative code/docs.
- Integration test running pipeline on sample repo (like Dazzle) ensuring no timeouts or memory blowups.
- Benchmark harness to track runtime vs. file size.

## 13. Open Questions

- Do we need per-language registries (e.g., `.py` vs `.pyi`)?
- Should summarization integrate directly into pipeline or remain in KB build script?
- How aggressively should we cache chunk results (hash by content) to avoid recomputation when files don’t change?
- How do we expose chunk metadata in downstream tools (UI, Slack bot) for debugging?

---

**Next Steps:**
- Finalize `ChunkerConfig` shape and default values.
- Implement Phase 1 (sliding window + pipeline scaffolding).
- Write tests ensuring no regression against current KB build.
- Incrementally add higher-level chunkers in Phase 2.
