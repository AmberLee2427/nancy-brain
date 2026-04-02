# Knowledge Base Management Scripts

Nancy Brain treats PDF OCR as a **separate artifact-generation stage**. The main
build pipeline consumes cached OCR Markdown and stays compatible with CPU-only
hosts, while OCR runs in an optional worker runtime.

## Recommended Two-Stage Workflow

### Stage 1: Warm OCR Artifacts

Run OCR on a worker machine, GPU node, or container:

```bash
nancy-brain ocr setup
nancy-brain ocr warm --articles-config config/articles.yml
```

This stage:

1. downloads article PDFs
2. computes content hashes
3. generates Markdown for missing or stale PDFs
4. writes artifacts into `knowledge_base/cache/pdf_ocr`

### Stage 2: Build the Knowledge Base

Run the normal build anywhere, including a CPU-only MCP host:

```bash
nancy-brain build --articles-config config/articles.yml --use-cached-ocr-only
```

This stage:

1. clones or updates repositories
2. reads OCR Markdown from cache
3. chunks/indexes repos and papers together
4. builds embeddings without importing the OCR backend

## Core Scripts and Commands

| Command | Purpose |
| --- | --- |
| `nancy-brain build` | Build or refresh the knowledge base |
| `nancy-brain build --repo <name>` | Rebuild one named repository only |
| `nancy-brain build --use-cached-ocr-only` | Build from existing OCR artifacts only |
| `nancy-brain ocr warm` | Produce/update cached OCR Markdown for PDFs |
| `python scripts/manage_repositories.py` | Clone/update/list repositories from config |
| `python scripts/manage_articles.py` | Manual add/list/remove for local PDFs |

## Configuration Files

### `config/repositories.yml`

```yaml
microlensing_tools:
  - name: pyLIMA
    url: https://github.com/ebachelet/pyLIMA.git

jupyter_notebooks:
  - name: roman_notebooks
    url: https://github.com/spacetelescope/roman_notebooks.git
```

### `config/articles.yml`

```yaml
journal_articles:
  - name: "Paczynski_1986_ApJ_304_1"
    url: "https://ui.adsabs.harvard.edu/link_gateway/1986ApJ...304....1P/PUB_PDF"
    description: "Paczynski (1986) - Gravitational microlensing by the galactic halo"

roman_mission:
  - name: "Spergel_2015_arXiv_1503.03757"
    url: "https://arxiv.org/pdf/1503.03757.pdf"
    description: "Roman mission report"
```

## File Organization

```text
knowledge_base/
├── raw/
│   ├── microlensing_tools/
│   └── journal_articles/
├── cache/
│   ├── summaries/
│   └── pdf_ocr/
│       └── <content-hash>/
│           ├── content.md
│           └── metadata.json
└── embeddings/
    ├── index/
    └── code_index/
```

## Installation Model

### Core Build / MCP Host

```bash
pip install nancy-brain
```

Use this on:

- local developer machines
- CPU-only servers
- the machine hosting the MCP server

### Optional OCR Worker

The default package path is a managed shared worker runtime:

```bash
nancy-brain ocr setup
nancy-brain ocr status --verify
```

This creates an isolated OCR runtime under the standard shared-worker path, so
the main `nancy-brain` env stays compatible with `txtai` and CPU-only hosts.

Advanced/manual options still exist if you want to manage OCR yourself:

```bash
pip install "nancy-brain[ocr-gpu]"
```

In practice, many deployments use a separate conda env or Apptainer image for
the OCR worker so that DeepSeek/Nougat dependencies do not conflict with the
main indexing stack.

## High-Value Usage Patterns

### Cluster preprocess, local build

```bash
# Worker node
nancy-brain ocr setup
nancy-brain ocr warm --articles-config config/articles.yml

# Sync cache home
rsync -av knowledge_base/cache/pdf_ocr/ nuc:/path/to/project/knowledge_base/cache/pdf_ocr/

# CPU host
nancy-brain build --articles-config config/articles.yml --use-cached-ocr-only
```

### Scoped rebuild on the MCP host

```bash
nancy-brain build --repo MulensModel --use-cached-ocr-only
```

### Force article refresh

```bash
nancy-brain ocr warm --articles-config config/articles.yml --force-update
```

## Troubleshooting

### OCR Artifacts Missing

If PDFs are configured but OCR artifacts do not exist:

```bash
nancy-brain ocr setup
nancy-brain ocr warm --articles-config config/articles.yml
```

or re-run the build with an external worker configured.

### OCR Worker Environment Issues

Keep the OCR runtime isolated. DeepSeek/Nougat dependencies are intentionally
separate from the main `txtai`/embedding environment.

### Article URL Problems

- some publisher links return HTML or require auth
- arXiv links are usually the most stable
- deleting a hash entry under `knowledge_base/cache/pdf_ocr` forces re-processing
