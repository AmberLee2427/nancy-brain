"""Article import utilities for populating config/articles.yml."""

from __future__ import annotations

import io
import logging
import os
import re
import time
import unicodedata
import urllib.parse
import xml.etree.ElementTree as ET
from pathlib import Path

import click
import requests
import yaml

LOGGER = logging.getLogger(__name__)

ARXIV_API_BASE = "http://export.arxiv.org/api/query"
ADS_API_BASE = "https://api.adsabs.harvard.edu/v1"
ATOM_NS = "http://www.w3.org/2005/Atom"


def _sanitize(value: str) -> str:
    """Return a filesystem-safe token made of letters, digits, and underscores."""
    if not value:
        return ""
    sanitized = re.sub(r"[^0-9A-Za-z]+", "_", value)
    return sanitized.strip("_")


def _make_name(first_author_surname: str, year: str, arxiv_id: str | None = None, doi: str | None = None) -> str:
    """Construct a sanitized article name with stable import conventions."""
    surname = first_author_surname or "Unknown"
    surname = unicodedata.normalize("NFKD", surname).encode("ascii", "ignore").decode()
    surname = _sanitize(surname) or "Unknown"

    year_match = re.search(r"\d{4}", str(year or ""))
    year_token = year_match.group(0) if year_match else "Unknown"

    if arxiv_id:
        arxiv_token = _sanitize(str(arxiv_id).replace(".", "_")) or "unknown"
        name = f"{surname}_{year_token}_arXiv_{arxiv_token}"
    elif doi:
        name = f"{surname}_{year_token}"
    else:
        name = f"{surname}_{year_token}"

    name = _sanitize(name)
    if len(name) > 80:
        name = name[:80].strip("_")
    return name or "Unknown_Unknown"


def _chunks(items: list[str], size: int) -> list[list[str]]:
    return [items[i : i + size] for i in range(0, len(items), size)]


def _dedupe_preserve_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        result.append(item)
    return result


def _normalize_arxiv_id(value: str | None) -> str | None:
    if not value:
        return None
    normalized = value.strip()
    normalized = re.sub(r"^arxiv\s*:\s*", "", normalized, flags=re.IGNORECASE)

    url_match = re.search(r"arxiv\.org/(?:abs|pdf)/([^?#]+)", normalized, flags=re.IGNORECASE)
    if url_match:
        normalized = url_match.group(1)

    normalized = re.sub(r"\.pdf$", "", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"v\d+$", "", normalized, flags=re.IGNORECASE)
    normalized = normalized.strip()
    return normalized or None


def _looks_like_arxiv_id(value: str | None) -> bool:
    if not value:
        return False
    token = value.strip()
    if token.lower().startswith("arxiv:") or "arxiv.org" in token.lower():
        return True
    if re.match(r"^\d{4}\.\d{4,5}(v\d+)?$", token, flags=re.IGNORECASE):
        return True
    if re.match(r"^[a-z\-]+(?:\.[a-z\-]+)?/\d{7}(v\d+)?$", token, flags=re.IGNORECASE):
        return True
    return False


def _first_author_surname(author_value: str | None) -> str:
    if not author_value:
        return "Unknown"
    first_author = author_value.split(" and ")[0].strip()
    if not first_author:
        return "Unknown"
    if "," in first_author:
        surname = first_author.split(",", 1)[0].strip()
    else:
        surname = first_author.split()[-1].strip()
    return surname or "Unknown"


def _extract_year(raw_value: str | None) -> str:
    if not raw_value:
        return "Unknown"
    match = re.search(r"\d{4}", str(raw_value))
    return match.group(0) if match else "Unknown"


def _clean_text(text: str | None) -> str:
    if not text:
        return ""
    return re.sub(r"\s+", " ", text.replace("{", "").replace("}", " ")).strip()


def _normalize_title_for_compare(title: str | None) -> str:
    if not title:
        return ""
    return re.sub(r"[^a-z0-9]+", "", title.lower())


def _parse_bibtex_entries(bib_path: Path) -> list[dict[str, str]]:
    """Parse BibTeX entries using bibtexparser when available, else a minimal fallback parser."""
    text = bib_path.read_text(encoding="utf-8")

    try:
        import bibtexparser  # type: ignore

        if hasattr(bibtexparser, "parse_file"):
            library = bibtexparser.parse_file(str(bib_path))
            parsed_entries: list[dict[str, str]] = []
            for entry in getattr(library, "entries", []):
                fields = getattr(entry, "fields", None)
                if fields is None:
                    continue
                parsed: dict[str, str] = {}
                for field in fields:
                    key = str(getattr(field, "key", "")).lower().strip()
                    if not key:
                        continue
                    parsed[key] = str(getattr(field, "value", "") or "").strip()
                if parsed:
                    parsed_entries.append(parsed)
            if parsed_entries:
                return parsed_entries

        if hasattr(bibtexparser, "load"):
            from bibtexparser.bparser import BibTexParser  # type: ignore

            parser = BibTexParser(common_strings=True)
            db = bibtexparser.load(io.StringIO(text), parser=parser)
            return [{str(k).lower(): str(v) for k, v in entry.items()} for entry in db.entries]
    except Exception as exc:
        LOGGER.debug("Falling back to regex BibTeX parser: %s", exc)

    entries: list[dict[str, str]] = []
    cursor = 0
    while True:
        at_pos = text.find("@", cursor)
        if at_pos == -1:
            break
        open_brace = text.find("{", at_pos)
        if open_brace == -1:
            break
        header_comma = text.find(",", open_brace)
        if header_comma == -1:
            break

        depth = 1
        index = open_brace + 1
        while index < len(text) and depth > 0:
            if text[index] == "{":
                depth += 1
            elif text[index] == "}":
                depth -= 1
            index += 1

        if depth != 0:
            break

        body = text[header_comma + 1 : index - 1]
        cursor = index

        parsed: dict[str, str] = {}
        field_cursor = 0
        while field_cursor < len(body):
            while field_cursor < len(body) and body[field_cursor] in " \t\r\n,":
                field_cursor += 1
            if field_cursor >= len(body):
                break

            key_start = field_cursor
            while field_cursor < len(body) and re.match(r"[A-Za-z0-9_-]", body[field_cursor]):
                field_cursor += 1
            key = body[key_start:field_cursor].strip().lower()
            if not key:
                break

            while field_cursor < len(body) and body[field_cursor].isspace():
                field_cursor += 1
            if field_cursor >= len(body) or body[field_cursor] != "=":
                next_comma = body.find(",", field_cursor)
                if next_comma == -1:
                    break
                field_cursor = next_comma + 1
                continue
            field_cursor += 1

            while field_cursor < len(body) and body[field_cursor].isspace():
                field_cursor += 1
            if field_cursor >= len(body):
                break

            if body[field_cursor] == "{":
                value_depth = 1
                value_start = field_cursor + 1
                field_cursor += 1
                while field_cursor < len(body) and value_depth > 0:
                    if body[field_cursor] == "{":
                        value_depth += 1
                    elif body[field_cursor] == "}":
                        value_depth -= 1
                    field_cursor += 1
                raw_value = body[value_start : field_cursor - 1]
            elif body[field_cursor] == '"':
                value_start = field_cursor + 1
                field_cursor += 1
                while field_cursor < len(body):
                    if body[field_cursor] == '"' and body[field_cursor - 1] != "\\":
                        break
                    field_cursor += 1
                raw_value = body[value_start:field_cursor]
                if field_cursor < len(body):
                    field_cursor += 1
            else:
                value_start = field_cursor
                while field_cursor < len(body) and body[field_cursor] not in ",\n":
                    field_cursor += 1
                raw_value = body[value_start:field_cursor]

            parsed[key] = raw_value.strip()

            while field_cursor < len(body) and body[field_cursor] != ",":
                field_cursor += 1
            if field_cursor < len(body) and body[field_cursor] == ",":
                field_cursor += 1

        if parsed:
            entries.append(parsed)

    return entries


def _build_description(title: str, first_author: str, year: str) -> str:
    title = _clean_text(title)
    author = _clean_text(first_author) or "Unknown"
    year_token = _extract_year(year)
    if title and year_token != "Unknown":
        return f"{author} ({year_token}) - {title}"
    if title:
        return f"{author} - {title}"
    return f"{author} ({year_token})"


def _parse_arxiv_atom(xml_text: str) -> list[dict[str, str]]:
    root = ET.fromstring(xml_text)
    results: list[dict[str, str]] = []

    for entry in root.findall(f"{{{ATOM_NS}}}entry"):
        raw_id = (entry.findtext(f"{{{ATOM_NS}}}id") or "").strip()
        arxiv_id = raw_id
        if "/abs/" in arxiv_id:
            arxiv_id = arxiv_id.split("/abs/", 1)[1]
        arxiv_id = arxiv_id.split("?", 1)[0]
        arxiv_id = re.sub(r"v\d+$", "", arxiv_id)

        title = _clean_text(entry.findtext(f"{{{ATOM_NS}}}title"))
        # Skip arXiv error-feed entries – they are not real papers
        if title.lower() == "error":
            continue
        authors = entry.findall(f"{{{ATOM_NS}}}author")
        first_author = "Unknown"
        if authors:
            first_name = _clean_text(authors[0].findtext(f"{{{ATOM_NS}}}name"))
            first_author = _first_author_surname(first_name)

        published = _clean_text(entry.findtext(f"{{{ATOM_NS}}}published"))
        year = _extract_year(published)

        pdf_url = None
        for link in entry.findall(f"{{{ATOM_NS}}}link"):
            if link.get("title") != "pdf":
                continue
            href = (link.get("href") or "").strip()
            if not href:
                continue
            href = re.sub(r"v\d+$", "", href)
            href = href.replace("http://", "https://", 1)
            if not href.endswith(".pdf"):
                href = f"https://arxiv.org/pdf/{arxiv_id}.pdf"
            pdf_url = href
            break
        if not pdf_url and arxiv_id:
            pdf_url = f"https://arxiv.org/pdf/{arxiv_id}.pdf"

        results.append(
            {
                "arxiv_id": arxiv_id,
                "title": title,
                "first_author": first_author,
                "year": year,
                "pdf_url": pdf_url,
            }
        )

    return results


def arxiv_lookup(id_list: list[str]) -> list[dict[str, str]]:
    """Return a list of normalized arXiv records for provided IDs."""
    cleaned_ids = [_normalize_arxiv_id(item) for item in id_list]
    cleaned_ids = [item for item in cleaned_ids if item]
    if not cleaned_ids:
        return []

    params = urllib.parse.urlencode(
        {
            "id_list": ",".join(cleaned_ids),
            "max_results": len(cleaned_ids),
        }
    )
    url = f"{ARXIV_API_BASE}?{params}"
    response = requests.get(url, timeout=20)
    response.raise_for_status()
    results = _parse_arxiv_atom(response.text)
    time.sleep(3)
    return results


def _arxiv_title_search(title: str) -> dict[str, str] | None:
    cleaned_title = _clean_text(title)
    if not cleaned_title:
        return None

    title_query = urllib.parse.quote(f'ti:"{cleaned_title}"')
    url = f"{ARXIV_API_BASE}?search_query={title_query}&max_results=3"
    response = requests.get(url, timeout=20)
    response.raise_for_status()
    results = _parse_arxiv_atom(response.text)
    time.sleep(3)

    if len(results) != 1:
        return None

    candidate = results[0]
    if _normalize_title_for_compare(candidate.get("title")) != _normalize_title_for_compare(cleaned_title):
        return None
    return candidate


def _load_articles_yaml(output_path: Path) -> dict:
    if not output_path.exists():
        return {}
    with output_path.open("r", encoding="utf-8") as handle:
        loaded = yaml.safe_load(handle) or {}
    if not isinstance(loaded, dict):
        raise click.ClickException(f"Invalid YAML structure in {output_path}; expected top-level mapping.")
    return loaded


def _merge_entries(data: dict, category: str, entries: list[dict[str, str]]) -> tuple[int, int]:
    category_entries = data.setdefault(category, [])
    if not isinstance(category_entries, list):
        raise click.ClickException(f"Invalid category '{category}' in articles YAML; expected a list.")

    existing_names = {item.get("name") for item in category_entries if isinstance(item, dict)}
    added = 0
    skipped_duplicate = 0

    for entry in entries:
        name = entry.get("name")
        if not name:
            skipped_duplicate += 1
            continue
        if name in existing_names:
            skipped_duplicate += 1
            continue
        category_entries.append(entry)
        existing_names.add(name)
        added += 1

    return added, skipped_duplicate


def _write_articles_yaml(output_path: Path, data: dict) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as handle:
        yaml.dump(data, handle, default_flow_style=False, allow_unicode=True, sort_keys=False)


def _entry_arxiv_id(entry: dict[str, str]) -> str | None:
    archive_prefix = (entry.get("archiveprefix") or "").strip().lower()
    candidates: list[str] = []

    for key in ("arxiv_id", "arxivid"):
        if entry.get(key):
            candidates.append(entry[key])

    eprint = entry.get("eprint")
    if eprint and (archive_prefix == "arxiv" or _looks_like_arxiv_id(eprint)):
        candidates.append(eprint)

    if entry.get("url"):
        candidates.append(entry["url"])

    for candidate in candidates:
        normalized = _normalize_arxiv_id(candidate)
        if normalized:
            return normalized
    return None


def import_from_bibtex(
    bib_path: str | Path,
    category: str,
    output_path: str | Path,
    dry_run: bool = False,
) -> dict[str, object]:
    """Import articles from a BibTeX file into a YAML articles catalog."""
    result: dict[str, object] = {
        "added": 0,
        "skipped_duplicate": 0,
        "skipped_no_url": 0,
        "errors": [],
    }

    bib_path = Path(bib_path)
    output_path = Path(output_path)
    if not bib_path.exists():
        raise click.ClickException(f"BibTeX file not found: {bib_path}")

    raw_entries = _parse_bibtex_entries(bib_path)

    parsed_entries: list[dict[str, str | None]] = []
    for raw_entry in raw_entries:
        title = _clean_text(raw_entry.get("title"))
        first_author = _first_author_surname(raw_entry.get("author"))
        year = _extract_year(raw_entry.get("year"))
        doi = (raw_entry.get("doi") or "").strip() or None
        arxiv_id = _entry_arxiv_id(raw_entry)

        parsed_entries.append(
            {
                "title": title,
                "first_author": first_author,
                "year": year,
                "doi": doi,
                "arxiv_id": arxiv_id,
            }
        )

    arxiv_ids = _dedupe_preserve_order([entry["arxiv_id"] for entry in parsed_entries if entry.get("arxiv_id")])
    arxiv_records: dict[str, dict[str, str]] = {}

    for id_chunk in _chunks(arxiv_ids, 20):
        try:
            lookup_results = arxiv_lookup(id_chunk)
            for item in lookup_results:
                item_id = _normalize_arxiv_id(item.get("arxiv_id"))
                if item_id:
                    arxiv_records[item_id] = item
        except Exception as exc:
            message = f"arXiv lookup failed for IDs {id_chunk}: {exc}"
            LOGGER.warning(message)
            result["errors"].append(message)

    entries_to_merge: list[dict[str, str]] = []

    for entry in parsed_entries:
        arxiv_id = entry.get("arxiv_id")
        if arxiv_id:
            metadata = arxiv_records.get(arxiv_id)
            if metadata:
                title = metadata.get("title") or entry.get("title") or ""
                first_author = metadata.get("first_author") or entry.get("first_author") or "Unknown"
                year = metadata.get("year") or entry.get("year") or "Unknown"
                url = metadata.get("pdf_url") or f"https://arxiv.org/pdf/{arxiv_id}.pdf"
            else:
                if not _looks_like_arxiv_id(arxiv_id):
                    result["skipped_no_url"] += 1
                    continue
                LOGGER.warning("No arXiv metadata found for '%s'; using BibTeX fields.", arxiv_id)
                title = entry.get("title") or ""
                first_author = entry.get("first_author") or "Unknown"
                year = entry.get("year") or "Unknown"
                url = f"https://arxiv.org/pdf/{arxiv_id}.pdf"

            if not url:
                result["skipped_no_url"] += 1
                continue

            entries_to_merge.append(
                {
                    "name": _make_name(first_author, year, arxiv_id=arxiv_id),
                    "url": url,
                    "description": _build_description(title, first_author, year),
                }
            )
            continue

        title = entry.get("title") or ""
        matched = None
        if title:
            try:
                matched = _arxiv_title_search(title)
            except Exception as exc:
                message = f"Title search failed for '{title}': {exc}"
                LOGGER.warning(message)
                result["errors"].append(message)

        if matched and matched.get("arxiv_id"):
            matched_id = _normalize_arxiv_id(matched.get("arxiv_id"))
            if matched_id:
                first_author = matched.get("first_author") or entry.get("first_author") or "Unknown"
                year = matched.get("year") or entry.get("year") or "Unknown"
                entries_to_merge.append(
                    {
                        "name": _make_name(first_author, year, arxiv_id=matched_id),
                        "url": matched.get("pdf_url") or f"https://arxiv.org/pdf/{matched_id}.pdf",
                        "description": _build_description(
                            matched.get("title") or title,
                            first_author,
                            year,
                        ),
                    }
                )
                continue

        doi = entry.get("doi")
        if doi:
            LOGGER.warning("Using DOI URL for '%s'; this may lead to a paywalled page.", doi)
            first_author = entry.get("first_author") or "Unknown"
            year = entry.get("year") or "Unknown"
            entries_to_merge.append(
                {
                    "name": _make_name(first_author, year, doi=doi),
                    "url": f"https://doi.org/{doi}",
                    "description": _build_description(title, first_author, year),
                }
            )
            continue

        result["skipped_no_url"] += 1

    data = _load_articles_yaml(output_path)
    added, skipped_duplicate = _merge_entries(data, category, entries_to_merge)
    result["added"] = added
    result["skipped_duplicate"] = skipped_duplicate

    if not dry_run:
        _write_articles_yaml(output_path, data)

    return result


def _ads_bigquery(bibcodes: list[str], headers: dict[str, str]) -> list[dict]:
    encoded = urllib.parse.urlencode(
        {
            "q": "*:*",
            "fl": "bibcode,title,author,identifier,doi,pubdate",
            "rows": len(bibcodes),
        }
    )
    payload = "bibcode\n" + "\n".join(bibcodes)
    response = requests.post(
        f"{ADS_API_BASE}/search/bigquery?{encoded}",
        headers={**headers, "Content-Type": "big-query/csv"},
        data=payload,
        timeout=60,
    )
    response.raise_for_status()
    return (response.json().get("response") or {}).get("docs") or []


def _first_list_item(value: object) -> str:
    if isinstance(value, list) and value:
        return str(value[0])
    if isinstance(value, str):
        return value
    return ""


def import_from_ads(
    library_name: str,
    category: str,
    output_path: str | Path,
    dry_run: bool = False,
) -> dict[str, object]:
    """Import ADS library documents into a YAML articles catalog."""
    token = os.environ.get("ADS_API_KEY")
    if not token:
        raise click.ClickException("ADS_API_KEY environment variable is not set.")

    result: dict[str, object] = {
        "added": 0,
        "skipped_duplicate": 0,
        "skipped_no_url": 0,
        "errors": [],
    }

    headers = {"Authorization": f"Bearer {token}"}

    try:
        response = requests.get(f"{ADS_API_BASE}/biblib/libraries", headers=headers, timeout=20)
        response.raise_for_status()
        libraries = response.json().get("libraries") or []
    except Exception as exc:
        raise click.ClickException(f"Failed to list ADS libraries: {exc}") from exc

    match = next((library for library in libraries if library.get("name") == library_name), None)
    if match is None:
        available = [library.get("name") for library in libraries]
        raise click.ClickException(f"ADS library '{library_name}' not found. Available: {available}")

    library_id = match.get("id")
    if not library_id:
        raise click.ClickException(f"ADS library '{library_name}' has no ID in API response.")

    try:
        response = requests.get(f"{ADS_API_BASE}/biblib/libraries/{library_id}", headers=headers, timeout=20)
        response.raise_for_status()
        details = response.json()
    except Exception as exc:
        raise click.ClickException(f"Failed to fetch ADS library '{library_name}': {exc}") from exc

    bibcodes = details.get("documents") or []
    metadata = details.get("metadata") or {}
    num_docs = int(metadata.get("num_documents") or len(bibcodes))

    if num_docs > len(bibcodes):
        try:
            response = requests.get(
                f"{ADS_API_BASE}/biblib/libraries/{library_id}?rows={num_docs}",
                headers=headers,
                timeout=30,
            )
            response.raise_for_status()
            bibcodes = response.json().get("documents") or []
        except Exception as exc:
            message = f"Failed to fetch all ADS library documents; using partial list: {exc}"
            LOGGER.warning(message)
            result["errors"].append(message)

    all_docs: list[dict] = []
    for bibcode_chunk in _chunks(list(bibcodes), 2000):
        if not bibcode_chunk:
            continue
        try:
            all_docs.extend(_ads_bigquery(bibcode_chunk, headers))
        except Exception as exc:
            message = f"ADS bigquery failed for {len(bibcode_chunk)} bibcodes: {exc}"
            LOGGER.warning(message)
            result["errors"].append(message)

    parsed_docs: list[dict[str, str | None]] = []
    for doc in all_docs:
        identifiers = doc.get("identifier") or []
        arxiv_id = next(
            (
                _normalize_arxiv_id(item.split(":", 1)[1])
                for item in identifiers
                if isinstance(item, str) and item.lower().startswith("arxiv:")
            ),
            None,
        )
        doi_values = doc.get("doi") or []
        doi = doi_values[0].strip() if doi_values else None

        title = _clean_text(_first_list_item(doc.get("title")))
        first_author = _first_author_surname(_first_list_item(doc.get("author")))
        year = _extract_year(str(doc.get("pubdate") or ""))

        parsed_docs.append(
            {
                "title": title,
                "first_author": first_author,
                "year": year,
                "doi": doi,
                "arxiv_id": arxiv_id,
            }
        )

    arxiv_ids = _dedupe_preserve_order([doc["arxiv_id"] for doc in parsed_docs if doc.get("arxiv_id")])
    arxiv_records: dict[str, dict[str, str]] = {}

    for id_chunk in _chunks(arxiv_ids, 20):
        try:
            lookup_results = arxiv_lookup(id_chunk)
            for item in lookup_results:
                item_id = _normalize_arxiv_id(item.get("arxiv_id"))
                if item_id:
                    arxiv_records[item_id] = item
        except Exception as exc:
            message = f"arXiv lookup failed for ADS IDs {id_chunk}: {exc}"
            LOGGER.warning(message)
            result["errors"].append(message)

    entries_to_merge: list[dict[str, str]] = []

    for doc in parsed_docs:
        arxiv_id = doc.get("arxiv_id")
        if arxiv_id:
            metadata_doc = arxiv_records.get(arxiv_id)
            if metadata_doc:
                title = metadata_doc.get("title") or doc.get("title") or ""
                first_author = metadata_doc.get("first_author") or doc.get("first_author") or "Unknown"
                year = metadata_doc.get("year") or doc.get("year") or "Unknown"
                url = metadata_doc.get("pdf_url") or f"https://arxiv.org/pdf/{arxiv_id}.pdf"
            else:
                title = doc.get("title") or ""
                first_author = doc.get("first_author") or "Unknown"
                year = doc.get("year") or "Unknown"
                url = f"https://arxiv.org/pdf/{arxiv_id}.pdf"

            entries_to_merge.append(
                {
                    "name": _make_name(first_author, year, arxiv_id=arxiv_id),
                    "url": url,
                    "description": _build_description(title, first_author, year),
                }
            )
            continue

        doi = doc.get("doi")
        if doi:
            LOGGER.warning("Using DOI URL for ADS document '%s'; this may lead to a paywalled page.", doi)
            first_author = doc.get("first_author") or "Unknown"
            year = doc.get("year") or "Unknown"
            entries_to_merge.append(
                {
                    "name": _make_name(first_author, year, doi=doi),
                    "url": f"https://doi.org/{doi}",
                    "description": _build_description(doc.get("title") or "", first_author, year),
                }
            )
            continue

        result["skipped_no_url"] += 1

    output_path = Path(output_path)
    data = _load_articles_yaml(output_path)
    added, skipped_duplicate = _merge_entries(data, category, entries_to_merge)
    result["added"] = added
    result["skipped_duplicate"] = skipped_duplicate

    if not dry_run:
        _write_articles_yaml(output_path, data)

    return result
