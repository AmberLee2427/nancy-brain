# Nancy v2 — Development Plan (RAG core + HTTP + MCP)

## 0) Architecture (one brain, two plugs)

```
nancy-brain/
├─ rag_core/                 # pure Python library (no web, no Slack, no MCP)
│  ├─ service.py             # RAGService: search/retrieve/tree/weights/version
│  ├─ registry.py            # doc_id → {repo, default_branch, toolkit, doctype, github_url, sha256, line_index}
│  ├─ store.py               # read-only content store; span extraction by line offsets
│  ├─ search.py              # txtai wrapper (dual embeddings optional), filtering, scoring
│  └─ types.py               # SearchHit, Passage, DocMeta dataclasses
├─ connectors/
│  ├─ http_api/              # FastAPI thin wrapper for GPT Actions & Slack
│  │  ├─ app.py
│  │  └─ schemas.py
│  └─ mcp_server/            # MCP thin wrapper (tools/resources) for MCP clients
│     └─ server.py
├─ scripts/
│  ├─ build_index.py         # clone/update repos, build registry, compute line_index & sha256, build embeddings
│  └─ verify_index.py        # sanity checks (branch names, missing files, hash drift)
└─ config/
   ├─ repositories.yml       # (your YAML above)
   ├─ weights.yaml
   └─ index.meta.json        # produced by build; holds index_version/build_sha
```

**Design rule:** **Connectors never read the filesystem.** They only call `rag_core.RAGService`.

---

## 1) RAG core (reference-only, deterministic)

**Public API** (what both connectors call):

```python
class RAGService:
    def search(self, query: str, *, limit: int = 6,
               toolkit: str | None = None,   # "mulensmodel"|"pylima"|"rtmodel"|None
               doctype: str | None = None,   # "paper"|"readme"|"notebook"|"doc"|"code"|None
               threshold: float = 0.0) -> list[SearchHit]: ...

    def retrieve(self, doc_id: str, *, start: int, end: int) -> Passage: ...
    def retrieve_batch(self, items: list[dict]) -> list[Passage]: ...
    def list_tree(self, prefix: str, *, depth: int = 2, max_entries: int = 500) -> list[dict]: ...
    def set_weight(self, doc_id: str, multiplier: float,
                   *, namespace: str = "global", ttl_days: int | None = None) -> None: ...

    def version(self) -> dict: ...  # {"index_version": "...", "build_sha": "...", "built_at": "..."}
    def health(self) -> dict: ...
```

**Key behaviors (all about citations, not execution):**

* **Doc identity is `doc_id`**, never raw paths. A **registry** (built from `repositories.yml` + local clones) maps `doc_id → DocMeta` with:

  * `github_url` **with correct default branch** (no “master” assumption),
  * `toolkit` (derived per repo: `MulensModel`→`mulensmodel`, `pyLIMA`→`pylima`, `RTModel`→`rtmodel`),
  * `doctype`,
  * `content_sha256`,
  * `line_index` (start offsets for each line).
* **Search returns hits** with short **snippets** and metadata.
* **Retrieve returns exact spans** (by line numbers) + `content_sha256` so a student’s citation is reproducible.
* **Filters** (`toolkit`, `doctype`) prune candidates **before** ranking so you don’t answer a pyLIMA question with MulensModel text.
* **Weights** are namespaced (`global` / `mulensmodel` / `pylima` / `rtmodel`) and can expire (TTL), so one loud user can’t permanently skew ranking.
* **No code execution.** The core never shells out to any repo. It’s read-only text.

---

## 2) HTTP connector (GPT Actions + Slack)

* **FastAPI**, OpenAPI **3.0.3**, unique `operationId`s.
* Endpoints: `/search` (GET), `/retrieve` (POST), `/retrieve/batch` (POST), `/tree` (GET), `/weight` (POST), `/version` (GET), `/health` (GET).
* Responses include `index_version` and, for `retrieve*`, `content_sha256`.
* **Auth** (bearer), gzip, small body caps, RFC7807 errors with `trace_id`.

*(You already have the shapes—this is just the thin wrapper around the core.)*

---

## 3) MCP connector (for future agent/IDE/Desktop)

* Tools mirror the core API (same argument names).
* Optionally expose KB as **resources** for read-only streaming of passages.
* Sessions cache `RAGService` instance; support cancellation.

---

## 4) Build pipeline

* `build_index.py`:

  1. Clone/update repos from `repositories.yml`.
  2. Detect **default branch** per repo (don’t assume).
  3. Walk files → compute `sha256`, `line_index`, `toolkit`, `doctype`; write `registry.jsonl`.
  4. Build txtai embeddings (general + optional code index).
  5. Emit `index.meta.json` with `index_version` = short hash of registry + embed configs.

---

## 5) Tests & guardrails

* Golden tests for **reference questions**:

  * “MulensModel PSPL parameter names” returns MulensModel docs, not pyLIMA.
  * “pyLIMA install with conda” returns the right README section + URL.
  * “RTModel config file location” returns span + correct branch URL.
* Enforce traversal safety (no `../`), max results, “insufficient evidence” when top score < τ.

---

# Your `rag_service.py` — does it work as-is?

It works for a **prototype**, but for Nancy-as-citation-machine you need three upgrades:

1. **Registry, not assumptions**

   * `_get_github_url` hardcodes `master`. Replace with a **registry** built at index time:

     ```python
     @dataclass(frozen=True)
     class DocMeta:
         doc_id: str
         github_url: str
         default_branch: str
         toolkit: str | None
         doctype: str
         content_sha256: str
         line_index: list[int]
     ```

     Keep a dict `self.registry[doc_id] = DocMeta`. Then:

     ```python
     def github_url(self, doc_id: str) -> str:
         return self.registry[doc_id].github_url
     ```

2. **Deterministic spans**

   * Right now you never **retrieve** by `(doc_id, start, end)`; you only echo vector chunks. Add:

     ```python
     def retrieve(self, doc_id: str, *, start: int, end: int) -> dict:
         meta = self.registry[doc_id]
         text = self.store.read_lines(doc_id, start, end)   # uses meta.line_index
         return {"doc_id": doc_id, "start": start, "end": end,
                 "text": text, "github_url": meta.github_url,
                 "content_sha256": meta.content_sha256,
                 "index_version": self.index_version}
     ```

     And a `retrieve_batch(...)` twin. This is still **reference-only**.

3. **Toolkit & type filters**

   * Add `toolkit` and `doctype` params to `search(...)` and apply them **pre-rank** using `self.registry`.

Quality-of-life tidy-ups:

* Map repo→toolkit once (MulensModel→`mulensmodel`, pyLIMA→`pylima`, RTModel→`rtmodel`).
* Don’t assume “code vs docs” from extension alone; let the registry label `doctype`.
* Expose `version()` returning `index_version/build_sha/built_at` and include `index_version` in hits and passages.

If you want quick deltas without a full refactor, **keep your current search**, but:

* Replace `_get_github_url` with a registry lookup,
* Add a light `retrieve(doc_id, start, end)`,
* Thread `toolkit`/`doctype` filters into your search candidate set,
* Return `content_sha256` with every retrieve for reproducible citations.

That’s it. You keep Nancy’s soul—**point people to the right lines in the right repos**—and you add just enough skeleton so Slack, GPT Actions, and MCP all drink from the same well without stepping on your toes.
