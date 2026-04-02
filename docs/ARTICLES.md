# Journal Article Management

Journal articles are handled as **PDF sources plus cached OCR Markdown artifacts**.
The main `nancy-brain` build consumes cached Markdown; OCR itself runs in an
optional worker runtime.

This split exists so that:

- CPU-only hosts can still build and serve the knowledge base
- `txtai` and the embedding stack do not have to share a Python env with GPU OCR
- cluster pre-processing can warm OCR artifacts once and reuse them everywhere

## Recommended Workflow

### 1. Configure Article PDFs

Add article URLs to `config/articles.yml`:

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

### 2. Warm OCR Artifacts on a Worker

Run OCR in a dedicated worker env or container:

```bash
nancy-brain ocr warm --articles-config config/articles.yml
```

Typical worker setups:

- GPU cluster node running DeepSeek OCR
- CPU worker env running Nougat
- Apptainer/Singularity image on HPC

The worker writes Markdown cache artifacts under:

`knowledge_base/cache/pdf_ocr/`

### 3. Build on the Main Host

Build the searchable KB from cached OCR artifacts:

```bash
nancy-brain build --articles-config config/articles.yml --use-cached-ocr-only
```

This is the recommended mode for:

- CPU-only MCP hosts
- scoped rebuilds on small machines
- reproducible rebuilds after cluster preprocessing

## Cache Contract

Each PDF is keyed by content hash. A cache entry contains:

- `content.md`: OCR Markdown
- `metadata.json`: backend/model/cache metadata

If a PDF changes, its content hash changes and the worker produces a new cache
entry automatically.

## Manual Article Imports

The individual article manager is still useful for ad hoc local PDFs:

```bash
python scripts/manage_articles.py add /path/to/paper.pdf
python scripts/manage_articles.py list
```

Manual imports still flow through the same OCR/cache boundary. Adding a PDF does
not require the main build env to import DeepSeek or Nougat directly.

## File Layout

```text
knowledge_base/
├── raw/
│   ├── journal_articles/          # Downloaded PDFs
│   └── roman_mission/
├── cache/
│   └── pdf_ocr/
│       └── <content-hash>/
│           ├── content.md
│           └── metadata.json
└── embeddings/
    ├── index/
    └── code_index/
```

## Operational Notes

- The main build env does not require Java or Apache Tika.
- OCR availability is optional for the build if cached Markdown is already present.
- Missing OCR artifacts can be deferred and warmed later on a worker node.
- Publisher URLs may still fail or return HTML; arXiv links are the most reliable.

## Common Patterns

### Cluster preprocess, local build

```bash
# On cluster / worker
nancy-brain ocr warm --articles-config config/articles.yml

# Sync OCR cache back to the MCP host
rsync -av knowledge_base/cache/pdf_ocr/ nuc:/path/to/project/knowledge_base/cache/pdf_ocr/

# On the MCP host
nancy-brain build --articles-config config/articles.yml --use-cached-ocr-only
```

### Scoped update on a CPU host

```bash
nancy-brain build --repo MulensModel --use-cached-ocr-only
```

### Force OCR refresh for changed PDFs

```bash
nancy-brain ocr warm --articles-config config/articles.yml --force-update
```
