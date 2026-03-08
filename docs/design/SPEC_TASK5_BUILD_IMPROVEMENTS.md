# Spec: Build Improvements (`--repo` filter, summary skips, `NB_SUMMARY_MODEL`)

This document is an implementation spec for a remote agent. Read it fully before
writing any code.

---

## Goal

Three related, incremental improvements to the `build` command:

1. **`--repo` filter** — allow the build to target a single repository within a
   category instead of processing all repositories.
2. **Summary skip guards** — avoid wasting LLM calls on tiny files or binary/data
   files that produce useless summaries.
3. **`NB_SUMMARY_MODEL` env var** — let operators point local summarisation at a
   larger model for better quality (GPU users).

---

## Files to modify

```
ref/nancy-brain/
├── nancy_brain/
│   ├── cli.py                    ← add --repo option to build command
│   └── summarization.py          ← read NB_SUMMARY_MODEL in _invoke_local()
├── scripts/
│   └── build_knowledge_base.py   ← add --repo arg, small-file + data-file guards
└── tests/
    └── test_build_improvements.py  ← NEW: unit/integration tests
```

---

## Change 1 — `--repo` filter

### 1a. `nancy_brain/cli.py`

Add one option to the `build` command:

```python
@click.option(
    "--repo",
    default=None,
    help="Limit build to a single repository by name (within the selected category).",
)
```

Thread it into the subprocess command list — find the section that builds `cmd`
and add:

```python
if repo:
    cmd.extend(["--repo", repo])
```

### 1b. `scripts/build_knowledge_base.py` — `main()`

In the `argparse` block, add:

```python
parser.add_argument(
    "--repo",
    default=None,
    help="Limit processing to one repository by name",
)
```

Pass `args.repo` as `repo_filter` to both `clone_repositories()` and
`build_txtai_index()`.

### 1c. `clone_repositories()` function signature

```python
def clone_repositories(
    config_path,
    base_path,
    dry_run=False,
    category=None,
    force_update=False,
    repo_filter=None,   # NEW
):
```

Inside the inner loop, after `repo_name = repo["name"]`, add:

```python
if repo_filter and repo_name != repo_filter:
    continue
```

### 1d. `build_txtai_index()` function signature

```python
def build_txtai_index(
    config_path,
    articles_config_path,
    base_path,
    embeddings_path,
    dry_run=False,
    category=None,
    summary_generator=None,
    repo_filter=None,    # NEW
):
```

Inside the inner repo loop (same pattern as `clone_repositories`):

```python
if repo_filter and repo_name != repo_filter:
    continue
```

---

## Change 2 — Summary skip guards

Both guards live in `build_txtai_index()`, just **before** the existing call to
`summary_generator.summarize(...)`.  They never prevent a file from being
**indexed** — they only skip the summary generation step.

### 2a. Add constants near the top of `build_knowledge_base.py`

```python
# Minimum content length (stripped) to bother generating a summary.
# Override with NB_MIN_SUMMARY_CHARS environment variable.
MIN_SUMMARY_CHARS = int(os.environ.get("NB_MIN_SUMMARY_CHARS", "200"))

# File extensions for which summary generation is never useful.
# These files are still indexed via their path/doc_id.
SUMMARY_SKIP_EXTENSIONS = {
    # Astronomy data
    ".fits", ".fit",
    # Numpy/scipy
    ".npy", ".npz",
    # Pickle
    ".pkl", ".pickle",
    # Tabular
    ".dat", ".csv", ".parquet",
    # HDF5
    ".hdf5", ".h5",
    # MATLAB / NIfTI
    ".mat", ".nii",
    # Archives
    ".gz", ".bz2", ".xz", ".zip", ".tar",
    # Compiled objects
    ".so", ".o", ".a", ".dylib", ".dll",
    # Images
    ".png", ".jpg", ".jpeg", ".gif", ".svg",
    ".ico", ".woff", ".woff2",
}
```

### 2b. Guard logic in `build_txtai_index()`

Find the block that checks `if summary_generator is not None and ...` and wrap
the inner summarize call:

```python
if (
    summary_generator is not None
    and summary_stats["enabled"]
    and doc_id not in summarized_docs
):
    # Guard 1: skip tiny files
    stripped = content.strip()
    if len(stripped) < MIN_SUMMARY_CHARS:
        logger.debug(
            "Skipping summary for %s: content too short (%d chars < %d)",
            doc_id, len(stripped), MIN_SUMMARY_CHARS,
        )
    # Guard 2: skip data/binary extensions
    elif file_path.suffix.lower() in SUMMARY_SKIP_EXTENSIONS:
        logger.debug(
            "Skipping summary for %s: extension %s in SUMMARY_SKIP_EXTENSIONS",
            doc_id, file_path.suffix.lower(),
        )
    else:
        summary = summary_generator.summarize(
            doc_id=doc_id, content=content, repo_name=repo_name, ...
        )
        ...  # rest of existing summary handling
```

Keep all the existing logic inside the `else` branch unchanged.

---

## Change 3 — `NB_SUMMARY_MODEL` environment variable

### `nancy_brain/summarization.py` — `_invoke_local()`

Locate the hardcoded line (approximately line 312):

```python
model_name = "Qwen/Qwen2.5-Coder-0.5B-Instruct"
```

Replace it with:

```python
model_name = os.environ.get(
    "NB_SUMMARY_MODEL",
    "Qwen/Qwen2.5-Coder-0.5B-Instruct",
)
```

`import os` is already at the top of the file.  No other change is needed; the
rest of `_invoke_local` already picks up `model_name` dynamically, applies
`device_map="auto"` and `torch.float16` when CUDA is available, so pointing to a
larger model (e.g. `Qwen/Qwen2.5-Coder-7B-Instruct`) just works.

Add a log line right after the model name resolution:

```python
logger.info("Local summary model: %s", model_name)
```

---

## Tests (`tests/test_build_improvements.py`)

Use `pytest`, `unittest.mock`, and `tmp_path`.  You do NOT need to invoke real
clones, LLM calls, or txtai indexing — mock the expensive operations.

| Test | What it checks |
|---|---|
| `test_repo_filter_skips_other_repos` | Call `clone_repositories()` with `repo_filter="target-repo"` and a config with 3 repos; assert only `target-repo` is cloned (check subprocess calls or function calls on the mock) |
| `test_repo_filter_none_processes_all` | `repo_filter=None` → all repos processed |
| `test_summary_skip_small_content` | Pass content shorter than `MIN_SUMMARY_CHARS` → `summary_generator.summarize` is **not** called |
| `test_summary_skip_data_extension` | File with `.fits` extension → `summarize` not called, but document is still appended to embeddings |
| `test_summary_not_skipped_for_normal_file` | Content ≥ `MIN_SUMMARY_CHARS` and `.py` extension → `summarize` **is** called |
| `test_nb_summary_model_env_var` | Set `NB_SUMMARY_MODEL=my/model` in env; call `_invoke_local()` mocking `AutoModelForCausalLM.from_pretrained`; assert it was called with `"my/model"` |
| `test_nb_summary_model_default` | Unset `NB_SUMMARY_MODEL`; assert default `"Qwen/Qwen2.5-Coder-0.5B-Instruct"` is used |
| `test_cli_repo_option_passed_to_subprocess` | Mock `subprocess.run`; call `nancy-brain build --repo my-repo`; assert `"--repo"` and `"my-repo"` appear in the captured command |

---

## Version bump

This is a patch release (no breaking changes):

- Update `pyproject.toml`: `version = "0.2.0"` → `version = "0.2.1"`.
- Prepend an entry to `CHANGELOG.md`:

```markdown
## [0.2.1] - <date>

### Added
- `--repo` option for `nancy-brain build` to limit processing to a single repository.
- `NB_SUMMARY_MODEL` environment variable for local summary model selection.
- `NB_MIN_SUMMARY_CHARS` environment variable to tune small-file summary skip threshold.

### Changed
- Summary generation now skips files shorter than `NB_MIN_SUMMARY_CHARS` (default 200 chars).
- Summary generation now skips known data/binary file extensions (`.fits`, `.npy`, `.csv`, etc.).
```

---

## Notes for agent

- The `build_txtai_index()` function is long (~300 lines); read it fully before
  editing to understand the exact structure of the summary guard block.
- The `summary_stats["enabled"]` gate already exists; the new guards nest inside
  it (see the guard logic above).
- `file_path` in `build_txtai_index` is a `pathlib.Path` object — `.suffix` and
  `.lower()` are safe to call directly.
- Do NOT change the indexing path — only the summarisation call is conditioned.
- Run `pytest tests/test_build_improvements.py -v` and fix all failures before
  finishing.
