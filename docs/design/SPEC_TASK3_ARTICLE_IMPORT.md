# Spec: Article Source Import (`import-bibtex` / `import-ads`)

This document is an implementation spec for a remote agent. Read it fully before
writing any code.

---

## Goal

Add two new CLI commands that populate `config/articles.yml` from external
bibliography sources, so users don't have to hand-edit YAML to add articles.

```
nancy-brain import-bibtex -f references.bib [--category CATEGORY] [--output config/articles.yml]
nancy-brain import-ads --library "My ADS Library" [--category CATEGORY] [--output config/articles.yml]
```

Both commands merge new entries into the existing `articles.yml` (or create it if
absent) without clobbering existing entries.

Both commands use two APIs — the **arXiv API** to enrich metadata and get verified
PDF links, and the **ADS API** for the library workflow.  Both APIs are called
with plain `requests`; no unofficial client libraries are required.

---

## Repository structure

```
ref/nancy-brain/
├── nancy_brain/
│   ├── cli.py                  ← add the two new @cli.command() functions here
│   └── article_import.py       ← NEW: parsing/resolution/API logic
├── scripts/
│   └── manage_articles.py      ← existing; leave it alone
├── config/
│   └── articles.yml            ← output target
└── tests/
    └── test_article_import.py  ← NEW: unit tests
```

---

## `articles.yml` format

The existing format (see `config/articles.yml`) is:

```yaml
<category>:
  - name: Spergel_2015_arXiv_1503.03757
    url: https://arxiv.org/pdf/1503.03757.pdf
    description: "Spergel et al. (2015) - Wide-Field InfrarRed Survey Telescope..."
```

- `name` must be a filesystem-safe identifier (no spaces or slashes).
- `url` must be a direct PDF URL.
- `description` is free text; use the paper title + first author + year if available.

**Naming convention for arXiv papers**: `{FirstAuthor}_{year}_arXiv_{arxiv_id}`
replacing dots in the arXiv ID with underscores, e.g. `arXiv_1503_03757`.

**Naming convention for DOI-only papers**: `{FirstAuthor}_{year}_{journal_abbrev}`
e.g. `Smith_2023_ApJ`. These may not have a downloadable PDF URL; log a warning
and skip.

---

## API Reference

### arXiv API

Base URL: `http://export.arxiv.org/api/query`
Authentication: none required.
Response: Atom 1.0 XML feed — parse with `xml.etree.ElementTree` (stdlib).
Rate limit: add a **3-second delay** between successive calls.

**Look up one or more IDs** (most reliable — use this whenever an arXiv ID is
already known):
```
GET http://export.arxiv.org/api/query?id_list=1503.03757,hep-ex/0307015
```

**Search by title** (fallback when no arXiv ID is known):
```
GET http://export.arxiv.org/api/query?search_query=ti:%22Some+Article+Title%22&max_results=3
```

**Parsing an Atom response**:
```python
import xml.etree.ElementTree as ET
import time

ATOM  = "http://www.w3.org/2005/Atom"
ARXIV = "http://arxiv.org/schemas/atom"

def arxiv_lookup(id_list: list[str]) -> list[dict]:
    """Return a list of {arxiv_id, title, first_author, year, pdf_url} dicts."""
    ids = ",".join(id_list)
    url = f"http://export.arxiv.org/api/query?id_list={ids}&max_results={len(id_list)}"
    resp = requests.get(url, timeout=20)
    resp.raise_for_status()
    root = ET.fromstring(resp.text)

    results = []
    for entry in root.findall(f"{{{ATOM}}}entry"):
        # arXiv ID: strip leading "http://arxiv.org/abs/"
        raw_id = entry.find(f"{{{ATOM}}}id").text.strip()
        arxiv_id = raw_id.replace("http://arxiv.org/abs/", "").split("v")[0]  # drop version

        title = entry.find(f"{{{ATOM}}}title").text.strip()
        authors = entry.findall(f"{{{ATOM}}}author")
        first_author = authors[0].find(f"{{{ATOM}}}name").text.strip() if authors else ""
        # surname only: last whitespace-delimited token
        surname = first_author.split()[-1] if first_author else "Unknown"

        published = entry.find(f"{{{ATOM}}}published").text  # ISO 8601
        year = published[:4]

        # PDF link: <link title="pdf" rel="related">
        pdf_url = None
        for link in entry.findall(f"{{{ATOM}}}link"):
            if link.get("title") == "pdf":
                # Use the versionless URL (latest version)
                href = link.get("href", "")
                pdf_url = re.sub(r"v\d+$", "", href)
                break
        if pdf_url is None:
            pdf_url = f"https://arxiv.org/pdf/{arxiv_id}"

        results.append({
            "arxiv_id": arxiv_id,
            "title": title,
            "first_author": surname,
            "year": year,
            "pdf_url": pdf_url,
        })
    time.sleep(3)  # be polite; arXiv TOS
    return results
```

### ADS API

Base URL: `https://api.adsabs.harvard.edu/v1`
Authentication: Bearer token from `ADS_API_KEY` environment variable.
All requests use `headers={"Authorization": "Bearer " + token}`.

**Step 1 — list all libraries** (GET, no body):
```
GET /biblib/libraries
```
Response JSON: `{"libraries": [{"id": "ABC123", "name": "My Library", ...}, ...]}`
Find the library whose `name` matches the user's `--library` argument.

**Step 2 — get bibcodes for a library** (GET, no body):
```
GET /biblib/libraries/{library_id}
```
Response JSON: `{"documents": ["2015arXiv150303757S", "1973PhRvD...7.2333B", ...], "metadata": {...}}`

**Step 3 — batch-resolve bibcodes to metadata** (POST bigquery, up to 2000 at a time):
```
POST /search/bigquery?q=*:*&fl=bibcode,title,author,identifier,doi,pubdate&rows=2000
Content-Type: big-query/csv

bibcode
2015arXiv150303757S
1973PhRvD...7.2333B
```

Response JSON: `{"response": {"docs": [{"bibcode": "...", "title": [...], "author": [...], "identifier": [...], "doi": [...], "pubdate": "..."}, ...]}}`

Key fields:
- `identifier`: list of alternate identifiers; arXiv IDs appear as `"arXiv:1503.03757"` 
- `doi`: list of DOI strings (may be empty)
- `author`: list of author name strings (last, first format)
- `title`: list with one element (the paper title)
- `pubdate`: ISO-ish date string, e.g. `"2015-02-00"` — extract first 4 chars for year

---

## Change 1 — New module `nancy_brain/article_import.py`

### Helper: `_make_name(first_author_surname, year, arxiv_id=None, doi=None)`

Construct a sanitized `name` field:
- arXiv: `{Surname}_{year}_arXiv_{arxiv_id_with_underscores}`
- DOI only: `{Surname}_{year}`
- Replace all non-alphanumeric chars with `_`, strip leading/trailing `_`, truncate to 80 chars.
- ASCII-normalise the surname via `unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()`.

### Helper: `_sanitize(s)` — same replacement logic, for field-level use.

---

### `import_from_bibtex(bib_path, category, output_path, dry_run=False) -> dict`

```
Parameters
----------
bib_path : str | Path
category : str
output_path : str | Path
dry_run : bool

Returns
-------
{"added": int, "skipped_duplicate": int, "skipped_no_url": int, "errors": list[str]}
```

**Step 1 — Parse .bib with `bibtexparser`**

Use `bibtexparser` to parse the file.  For each entry extract:
- `eprint` field (may contain bare arXiv ID like `1503.03757` or `hep-ex/0307015`)
- `archivePrefix` field (if `"arXiv"`, confirms `eprint` is an arXiv ID)
- `arxiv_id` or `arxivid` field (some exporters use this instead)
- `url` field (may contain `arxiv.org/abs/...`)
- `doi` field (fallback)
- `title`, `author`, `year` fields

Normalise the arXiv ID: strip any `arxiv:` prefix (case-insensitive), strip trailing
version (`v1`, `v2`, etc.), strip whitespace.

**Step 2 — Enrich with arXiv API**

Collect all entries that have an arXiv ID.  Batch them into groups of 20 and call
`arxiv_lookup(ids)`.  For entries the API confirms exist, use the API-returned
`title`, `first_author`, `year`, and `pdf_url` (overrides bib values; the API is
more reliable).  For entries the API returns no result for, log a warning and use
the bib values.

**Step 3 — Title search fallback**

For entries with no arXiv ID but with a `title`, call:
```
GET http://export.arxiv.org/api/query?search_query=ti:%22{title_url_encoded}%22&max_results=3
```
If exactly one result is returned and the title matches (case-insensitive, ignoring
punctuation), use that arXiv ID. Otherwise, fall through to DOI handling.

```python
import urllib.parse
title_query = urllib.parse.quote(f'ti:"{title}"')
url = f"http://export.arxiv.org/api/query?search_query={title_query}&max_results=3"
```

**Step 4 — DOI fallback**

Entries with no arXiv ID and no title match: if `doi` is present, set
`url = f"https://doi.org/{doi}"` and emit a warning that this may link to a paywall.
Entries with nothing useful: count as `skipped_no_url`.

**Step 5 — Merge and write**

Load the existing YAML (or start with `{}`), check for duplicates by `name` within the
target category (count as `skipped_duplicate`), append new entries, write back via:
```python
yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
```

**Dependencies to add to `pyproject.toml`** (core, not optional):
```toml
"bibtexparser>=2.0.0b7",
"requests>=2.28",   # already present; confirm it's listed
```

---

### `import_from_ads(library_name, category, output_path, dry_run=False) -> dict`

```
Parameters
----------
library_name : str      Name of the ADS private library to import.
category : str
output_path : str | Path
dry_run : bool

Returns
-------
{"added": int, "skipped_duplicate": int, "skipped_no_url": int, "errors": list[str]}
```

**Step 1 — Read token**

```python
token = os.environ.get("ADS_API_KEY")
if not token:
    raise click.ClickException("ADS_API_KEY environment variable is not set.")
headers = {"Authorization": f"Bearer {token}"}
```

**Step 2 — Find library by name**

```python
resp = requests.get("https://api.adsabs.harvard.edu/v1/biblib/libraries",
                    headers=headers, timeout=20)
resp.raise_for_status()
libraries = resp.json()["libraries"]
match = next((lib for lib in libraries if lib["name"] == library_name), None)
if match is None:
    raise click.ClickException(f"ADS library '{library_name}' not found. "
                               f"Available: {[l['name'] for l in libraries]}")
library_id = match["id"]
```

**Step 3 — Get bibcodes**

```python
resp = requests.get(f"https://api.adsabs.harvard.edu/v1/biblib/libraries/{library_id}",
                    headers=headers, timeout=20)
resp.raise_for_status()
bibcodes = resp.json()["documents"]   # list of strings
```

Note: by default the `/biblib/libraries/{id}` endpoint returns up to 20 documents.
To get all documents, pass `?rows=10000` (or however many `num_documents` reports):
```python
num_docs = resp.json()["metadata"]["num_documents"]
resp = requests.get(f"https://api.adsabs.harvard.edu/v1/biblib/libraries/{library_id}?rows={num_docs}",
                    headers=headers, timeout=30)
bibcodes = resp.json()["documents"]
```

**Step 4 — Batch-resolve bibcodes via bigquery**

Process in chunks of 2000 (ADS limit per request):
```python
import urllib.parse

def _ads_bigquery(bibcodes: list[str], headers: dict) -> list[dict]:
    encoded = urllib.parse.urlencode({
        "q": "*:*",
        "fl": "bibcode,title,author,identifier,doi,pubdate",
        "rows": len(bibcodes),
    })
    payload = "bibcode\n" + "\n".join(bibcodes)
    resp = requests.post(
        f"https://api.adsabs.harvard.edu/v1/search/bigquery?{encoded}",
        headers={**headers, "Content-Type": "big-query/csv"},
        data=payload,
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json()["response"]["docs"]
```

**Step 5 — Extract arXiv IDs from identifier field**

```python
for doc in docs:
    identifiers = doc.get("identifier") or []
    arxiv_id = next(
        (s.split(":", 1)[1] for s in identifiers if s.lower().startswith("arxiv:")),
        None,
    )
    doi_list = doc.get("doi") or []
    doi = doi_list[0] if doi_list else None
    ...
```

**Step 6 — Enrich arXiv papers via arXiv API**

For all docs with an arXiv ID, batch-call `arxiv_lookup()` (same helper as bibtex
importer) in groups of 20.  Use the arXiv API result for `title`, `first_author`,
`year`, `pdf_url` when available; fall back to ADS `title`/`author`/`pubdate` fields
otherwise.

For docs with no arXiv ID: use DOI URL as fallback or skip.

**Step 7 — Build entries and merge**

Same merge-and-write logic as `import_from_bibtex`.

---

## Change 2 — Add commands to `nancy_brain/cli.py`

```python
@cli.command("import-bibtex")
@click.option("-f", "--file", "bib_file", required=True, type=click.Path(exists=True),
              help="Path to the .bib file to import")
@click.option("--category", default="journal_articles",
              help="Category key in articles.yml (default: journal_articles)")
@click.option("--output", default="config/articles.yml",
              help="Path to articles.yml to update (default: config/articles.yml)")
@click.option("--dry-run", is_flag=True, help="Show what would be added without writing")
def import_bibtex(bib_file, category, output, dry_run):
    """Import articles from a BibTeX file into articles.yml."""
    ...


@cli.command("import-ads")
@click.option("--library", required=True, help="Name of the ADS private library to import")
@click.option("--category", default="journal_articles",
              help="Category key in articles.yml (default: journal_articles)")
@click.option("--output", default="config/articles.yml",
              help="Path to articles.yml to update (default: config/articles.yml)")
@click.option("--dry-run", is_flag=True, help="Show what would be added without writing")
def import_ads(library, category, output, dry_run):
    """Import articles from an ADS private library into articles.yml."""
    ...
```

Print a summary table of added/skipped/errors using click.echo. Exit 1 on fatal error.

---

## Tests (`tests/test_article_import.py`)

Use `tmp_path` and `unittest.mock.patch("requests.get")` / `patch("requests.post")`.
Do **not** make real network calls.  The arXiv API returns Atom XML; construct
minimal valid Atom responses in your fixtures.

| Test | What it checks |
|---|---|
| `test_bibtex_arxiv_entry` | Entry with `eprint = {1503.03757}` → arXiv API called with `id_list=1503.03757` → entry written with API-returned PDF URL |
| `test_bibtex_arxiv_with_prefix` | Entry with `eprint = {arXiv:1503.03757}` → prefix stripped before API call |
| `test_bibtex_title_fallback` | Entry with no arXiv ID but title → title search called → arXiv match used |
| `test_bibtex_doi_only_entry` | Entry with only a DOI → `url = https://doi.org/...` and a warning logged |
| `test_bibtex_duplicate_skipped` | Running import twice for the same entry → `skipped_duplicate = 1` on second run |
| `test_bibtex_name_sanitization` | Title with accented chars/spaces produces a clean `name` field |
| `test_bibtex_creates_yml_if_absent` | articles.yml created from scratch with correct structure |
| `test_bibtex_merges_into_existing` | Entries in other categories are preserved |
| `test_bibtex_dry_run_no_write` | `dry_run=True` does not write the file |
| `test_ads_library_lookup` | Mock GET /biblib/libraries → finds correct library ID |
| `test_ads_library_not_found` | Library name not in list → clear error message |
| `test_ads_bigquery_arxiv` | Mock bigquery response with arXiv identifier → arXiv API called → entry written |
| `test_ads_bigquery_doi_only` | Doc with no arXiv identifier but DOI → DOI URL used |
| `test_ads_missing_key` | Missing `ADS_API_KEY` → ClickException with clear message |

---

## Notes for agent

- Do not modify `manage_articles.py`.
- `bibtexparser` v2 has a different API from v1. The current PyPI release may be
  a beta (`2.0.0b7`); use the v2 API if available. If only v1 is installable, use
  v1 and note this in the code.
- The arXiv API `id_list` can include old-style IDs (`hep-ex/0307015`) as well as
  new-style (`1503.03757`). Both work.
- Strip the version suffix from arXiv IDs before storing (`1503.03757v2` → `1503.03757`).
  The versionless PDF URL always points to the latest version.
- ADS bigquery `Content-Type` must be `"big-query/csv"` exactly (see API docs).
- Run `pytest tests/test_article_import.py -v` and fix all failures before finishing.
