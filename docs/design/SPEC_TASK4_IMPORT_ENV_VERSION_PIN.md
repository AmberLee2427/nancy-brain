# Spec: Repository Version Pinning + `import-env` Command

This document is an implementation spec for a remote agent. Read it fully before
writing any code.

---

## Goal

Allow users to pin a specific git branch, tag, or commit for each repository in
`repositories.yml`.  Also add an `import-env` command that auto-populates
`repositories.yml` from a conda `environment.yml` file.

---

## Repository structure

```
ref/nancy-brain/
├── nancy_brain/
│   ├── cli.py                    ← add `import-env` command here
│   ├── config_validation.py      ← add optional `ref` field validation
│   └── env_import.py             ← NEW: environment.yml parsing + PyPI lookup
├── scripts/
│   ├── build_knowledge_base.py   ← update clone_repositories() for ref support
│   └── manage_repositories.py   ← update clone_repository() / update_repository()
├── config/
│   └── repositories.yml          ← add `ref:` examples in comments
└── tests/
    └── test_env_import.py        ← NEW: unit tests
```

---

## Part 1 — Version Pinning

### 1a. `repositories.yml` schema change

Add an **optional** `ref` field to each repository entry:

```yaml
roman_mission:
  - name: roman-coronagraph-instrument
    url: https://github.com/roman-corgi/roman_corgi_utils
    description: "Roman Coronagraph calibration utilities"
    ref: "v2.1.0"   # optional: branch, tag, or commit SHA
```

- `ref` is optional. If absent, behaviour is unchanged (latest default branch).
- `ref` may be a branch name (`main`, `develop`), a tag (`v2.1.0`), or a full
  commit SHA.

### 1b. `nancy_brain/config_validation.py`

In `validate_repositories_config`, add an optional field check after the
existing `name`/`url` checks:

```python
ref = repo.get("ref")
if ref is not None:
    if not isinstance(ref, str) or not ref.strip():
        errors.append(
            f"Repository '{repo.get('name', '?')}' in category '{cat}': "
            f"'ref' must be a non-empty string if present."
        )
```

Do not make `ref` required.  Adding it to the validator is belt-and-suspenders;
the rest of the code handles `None` gracefully.

### 1c. `scripts/manage_repositories.py`

In `RepositoryManager.clone_repository(repo_name, repo_url, repo_path)`:

```python
# Before:
cmd = ["git", "clone", repo_url, str(repo_path)]

# After:
ref = repo_config.get("ref") if repo_config else None
if ref:
    cmd = ["git", "clone", "--branch", ref, "--depth", "1", repo_url, str(repo_path)]
else:
    cmd = ["git", "clone", "--depth", "1", repo_url, str(repo_path)]
```

`repo_config` is the dict from `repositories.yml` for this repo.  Thread it
through from wherever `clone_repository` is called.

In `RepositoryManager.update_repository(repo_name, repo_path)`:

```python
# Before:
subprocess.run(["git", "pull", "origin", current_branch], ...)

# After:
ref = repo_config.get("ref") if repo_config else None
if ref:
    # Detach HEAD at the pinned ref.  Then re-attach if needed.
    subprocess.run(["git", "fetch", "--depth", "1", "origin", ref], ...)
    subprocess.run(["git", "checkout", ref], ...)
else:
    subprocess.run(["git", "pull", "origin", current_branch], ...)
```

Ensure the method signature accepts `repo_config=None` so call-sites that don't
pass a config dict continue to work.

### 1d. `scripts/build_knowledge_base.py`

In `clone_repositories()`:

```python
# When iterating repos, pass the full repo dict to clone/update helpers
for repo in repos:
    repo_name = repo["name"]
    repo_url  = repo["url"]
    ref       = repo.get("ref")   # may be None
    ...
    # Pass repo dict through to manage_repositories helpers so they can read ref
```

The details of how `ref` is threaded through depend on how `RepositoryManager`
methods are called.  Trace the call chain and add `repo_config=repo` at each
call site where a clone or update is triggered.

---

## Part 2 — `import-env` Command

### 2a. New module `nancy_brain/env_import.py`

Create this module with one public function:

```python
def import_from_env(
    env_file: str | Path,
    category: str | None,
    output_path: str | Path,
    dry_run: bool = False,
) -> dict:
    """
    Parse a conda environment.yml and add GitHub-backed packages to repositories.yml.

    Returns dict: {added: int, skipped_no_github: int, skipped_duplicate: int, errors: list[str]}
    """
```

**Parsing the environment file**:

```python
import yaml

with open(env_file) as f:
    env = yaml.safe_load(f)

env_name  = env.get("name", "imported")
effective_category = category or env_name

pip_packages = []
for dep in env.get("dependencies", []):
    if isinstance(dep, dict) and "pip" in dep:
        pip_packages.extend(dep["pip"])
```

For each string in `pip_packages`:
1. Strip version specifiers: `re.split(r"[=<>!~\[]", pkg)[0].strip()`
2. Skip `"."` (editable installs) and packages starting with `-e` or `-r` or `http`.
3. Query PyPI: `https://pypi.org/pypi/{package_name}/json` (GET, no auth).
4. From the JSON response, check `info.project_urls` for a key whose **value**
   contains `github.com`.  Try keys in this order: `Source`, `Source Code`,
   `Homepage`, `Repository`, then any remaining key.
5. If a GitHub URL is found, normalise it to `https://github.com/{owner}/{repo}`
   (strip trailing `.git`, query strings, fragment, extra path segments beyond 2).
6. Derive a `name` from the last two path segments: `{owner}_{repo}` (lower-cased,
   hyphens replaced with underscores).
7. Use `description = f"{package_name} — source from PyPI project_urls"`.
8. Use `ref = None` (no version pinning by default; the user can add it manually).

**Network error handling**: if the PyPI request fails (timeout, 404, etc.) skip
the package and add an entry to `errors`.

**Merging**: load the existing `repositories.yml`, check for duplicates by `url`
(not just `name`, since the same GitHub repo might be listed under a different
name already), append new entries, write back.

**Dependencies**: only `requests` and `pyyaml`, both already in the project.

### 2b. Add `import-env` command in `nancy_brain/cli.py`

```python
@cli.command("import-env")
@click.option("-f", "--file", "env_file", required=True, type=click.Path(exists=True),
              help="Path to the conda environment.yml file")
@click.option("--category", default=None,
              help="Override category key (default: conda env name)")
@click.option("--output", default="config/repositories.yml",
              help="Path to repositories.yml to update (default: config/repositories.yml)")
@click.option("--dry-run", is_flag=True, help="Show what would be added without writing")
def import_env(env_file, category, output, dry_run):
    """Scan a conda environment.yml and add GitHub-backed packages to repositories.yml."""
    ...
```

Call `env_import.import_from_env(...)`, print a rich (or plain) summary, exit 1
on fatal error.

---

## Tests (`tests/test_env_import.py`)

Use `tmp_path` and `unittest.mock.patch` (for `requests.get`).  Do not make real
network calls.

| Test | What it checks |
|---|---|
| `test_parse_conda_env` | A minimal `environment.yml` with pip packages is parsed correctly |
| `test_github_url_resolved` | A mocked PyPI response with `Source` pointing to GitHub produces correct `repositories.yml` entry |
| `test_no_github_url_skipped` | A package with no GitHub project URL is skipped (counted in `skipped_no_github`) |
| `test_editable_install_skipped` | `-e .` in the pip list is silently skipped |
| `test_duplicate_url_skipped` | Running import twice for the same package skips it on the second run (`skipped_duplicate`) |
| `test_ref_field_validation` | `validate_repositories_config` accepts a valid `ref` string and rejects an empty string |
| `test_ref_field_absent_passes` | Entries without `ref` still pass validation |
| `test_dry_run_no_write` | `dry_run=True` does not write to `repositories.yml` |
| `test_category_override` | `--category my_cat` uses `my_cat` rather than the conda env `name` field |

---

## Notes for agent

- `manage_repositories.py` currently calls `subprocess.run` directly with a
  hardcoded command list.  Add `repo_config` as an optional keyword argument
  (`None` default) and gate the `--branch` behaviour on `repo_config.get("ref")`
  to avoid breaking existing callers.
- The PyPI JSON API is unauthenticated and rate-limited at 360 req/min (generous
  for our use case).  Add a `time.sleep(0.1)` between requests to be polite.
- `--depth 1` is safe for tagged/branch clones.  For full commit SHAs, `--depth 1`
  does not work reliably; detect a 40-char hex string and skip `--depth` in that
  case, using `git clone` + `git checkout {sha}` instead.
- Run `pytest tests/test_env_import.py -v` and fix all failures before finishing.
