# SPEC TASK 6: External OCR Worker and Cache-First PDF Indexing

## Goal

Refactor PDF ingestion so that OCR is no longer part of the main build/runtime
environment. The core `nancy-brain` package should be able to build, search, and
serve a knowledge base on CPU-only hosts while consuming cached OCR Markdown
artifacts produced elsewhere.

This is primarily motivated by:

- `txtai` and the main indexing stack requiring newer `transformers`
- DeepSeek OCR requiring an older/custom `transformers` stack
- GPU/runtime instability (`flash_attn`, CUDA kernel compatibility)
- the need to run scoped MCP-host rebuilds on resource-limited machines
- the desire to ship `nancy-brain` as a reusable package, not a single fragile env

## Target Architecture

### Core Build Runtime

The main `nancy-brain` runtime is the CPU-friendly package used for:

- repository cloning and updates
- article download
- chunking
- embeddings/index build
- MCP serving
- scoped rebuilds on low-resource hosts

This runtime does **not** need DeepSeek, CUDA, `flash_attn`, or a GPU OCR stack.

### OCR Worker Runtime

OCR runs in a separate environment, subprocess, or container. The worker is
responsible for:

- rendering PDF pages
- running DeepSeek OCR on GPU when available
- running Nougat on CPU as fallback
- writing Markdown artifacts into the shared OCR cache

The default package behavior is a **local worker subprocess on the same machine**.
This is the primary UX target for users who install `nancy-brain` on a single
GPU workstation and expect `nancy-brain build` to just work.

Supported or planned launch modes:

- local subprocess in a separate env or runtime (**default**)
- local container / Apptainer image
- custom command wrapper
- remote worker / scheduler-backed execution (**future**)

### Cache Contract

The OCR cache remains the canonical interface between the worker and the build
pipeline:

`knowledge_base/cache/pdf_ocr/<content-hash>/`

Each entry stores:

- `content.md`: OCR Markdown
- `metadata.json`: backend, model, page count, cache key, timestamps, and status

The main build reads from this cache and never needs to import the OCR backend.

## User-Facing Workflow

### Default User Experience

For a user on a machine with a compatible NVIDIA GPU, the simplest supported
workflow should remain:

```bash
nancy-brain build --articles-config config/articles.yml
```

Under the hood, the build may spawn a local OCR worker subprocess, but the user
should not need to think about scheduler wrappers or remote execution for the
common single-machine case.

### CPU-only / MCP Host

The normal build path is cache-first:

```bash
nancy-brain build --articles-config config/articles.yml --use-cached-ocr-only
```

Behavior:

- use cached OCR Markdown if present
- index Markdown into the same chunking/embedding pipeline as repos
- skip or mark PDFs as `needs_ocr` if cache entries are missing

### OCR Warm on Cluster / Worker Node

```bash
nancy-brain ocr warm --articles-config config/articles.yml
```

Behavior:

- download or locate PDFs
- compute content hashes
- generate OCR Markdown for missing/stale PDFs
- update the shared OCR cache

### Scoped Update on the MCP Host

```bash
nancy-brain build --repo MulensModel --use-cached-ocr-only
```

This should work on a small CPU machine without re-running OCR.

## CLI and Runtime Changes

### New CLI Surface

Add a dedicated OCR command group:

```bash
nancy-brain ocr setup ...
nancy-brain ocr warm ...
nancy-brain ocr status ...
nancy-brain ocr worker ...
```

Proposed semantics:

- `ocr setup`: create/update the managed shared local OCR worker runtime
- `ocr warm`: produce/update cache artifacts for PDFs
- `ocr status`: report cached/missing/stale OCR state
- `ocr worker`: internal machine-readable entrypoint used by subprocess mode

### Default Worker Mode

The first implementation should target:

- **default mode**: local worker subprocess
- **configuration override**: custom worker command
- **deferred mode**: cache-only build when no worker is available

Remote-worker orchestration is explicitly not required for the first complete
package implementation.

### Worker Detection Order

The main app should detect a local OCR worker in this order:

1. `NB_OCR_WORKER_CMD`
2. project-level OCR worker config
3. a standard package-managed shared local worker install path
4. otherwise: no worker available

Notes:

- The package should **not** guess arbitrary sibling virtualenv names.
- The default should favor a **single shared worker runtime per machine**, not
  one OCR env per project, to avoid unnecessary package duplication on disk.
- If a compatible local worker is available, `nancy-brain build` should spawn it
  automatically by default.

### Build Flags

Add explicit build controls:

- `--use-cached-ocr-only`
- `--allow-missing-ocr`
- `--ocr-worker-cmd <command>`

Default package behavior should bias toward:

- cache-first on CPU hosts
- external worker if configured
- no in-process DeepSeek import in the main build env

## Implementation Phases

### Phase 1: Worker Boundary

- extract OCR execution into a worker entrypoint
- return structured JSON metadata/results
- keep current cache key/content-hash behavior
- make local worker subprocess spawning the default path
- implement the worker-detection order above

### Phase 2: Cache-First Build

- update `pdf_ocr.py` to:
  - read cache first
  - shell out to worker if configured
  - return `needs_ocr` when cache is missing and no worker is available
- keep Markdown as the canonical build input for PDFs

### Phase 3: Worker Backends

- move DeepSeek into the worker runtime
- add Nougat fallback in the same worker boundary
- keep backend selection entirely inside worker logic

### Phase 4: Cluster Workflow

- cluster jobs become OCR warm jobs plus CPU index build jobs
- the index build should only consume the cache
- sync `knowledge_base/cache/pdf_ocr` back to the MCP host for smoke tests

### Phase 5: Packaging

- keep `nancy-brain` install lightweight and `txtai`-compatible
- move OCR-specific dependencies into an isolated install path
- document separate worker env/container recommendations
- keep remote-worker support as future work, not a requirement for the first release

## Acceptance Criteria

- A CPU-only host can run `nancy-brain build --use-cached-ocr-only`
- The main build env does not need DeepSeek-compatible `transformers`
- OCR cache entries are portable across machines
- Scoped rebuilds on the MCP host do not require GPU OCR
- Cluster warm + cache sync + local rebuild works as an end-to-end smoke test
- Package docs make the split between core runtime and OCR worker explicit

## Non-Goals

- Solving all GPU compatibility issues inside the main package env
- Forcing DeepSeek and `txtai` to coexist in one Python environment
- Making GPU OCR a hard dependency for users who only want repo indexing or
  cached article ingestion
- Building remote-worker orchestration in the first Task 6 release
- Writing embeddings or summary cache from the OCR worker; the worker owns only
  the OCR Markdown cache contract
