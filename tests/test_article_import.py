"""Tests for article import workflows (BibTeX and ADS)."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from unittest.mock import patch

import click
import pytest
import requests
import yaml

from nancy_brain import article_import
from nancy_brain.article_import import import_from_ads, import_from_bibtex


class MockResponse:
    def __init__(self, json_data=None, text: str = "", status_code: int = 200):
        self._json_data = json_data
        self.text = text
        self.status_code = status_code

    def json(self):
        return self._json_data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")


def _atom_feed(entries: list[dict[str, str]]) -> str:
    entry_xml = []
    for entry in entries:
        arxiv_id = entry["arxiv_id"]
        title = entry.get("title", "Test Title")
        author = entry.get("author", "Test Author")
        year = entry.get("year", "2020")
        pdf_url = entry.get("pdf_url", f"http://arxiv.org/pdf/{arxiv_id}v1")
        entry_xml.append(f"""
  <entry>
    <id>http://arxiv.org/abs/{arxiv_id}v1</id>
    <title>{title}</title>
    <published>{year}-01-01T00:00:00Z</published>
    <author><name>{author}</name></author>
    <link title=\"pdf\" href=\"{pdf_url}\" />
  </entry>
""")

    return (
        "<?xml version='1.0' encoding='UTF-8'?>\n"
        "<feed xmlns='http://www.w3.org/2005/Atom'>\n" + "\n".join(entry_xml) + "\n</feed>"
    )


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr(article_import.time, "sleep", lambda _seconds: None)


def _write_bib(path: Path, content: str):
    path.write_text(content, encoding="utf-8")


def test_bibtex_arxiv_entry(tmp_path):
    bib = tmp_path / "refs.bib"
    _write_bib(
        bib,
        """
@article{spergel2015,
  title={WFIRST report},
  author={Spergel, David N. and Others},
  year={2015},
  eprint={1503.03757},
  archivePrefix={arXiv}
}
""",
    )

    output = tmp_path / "articles.yml"
    with patch(
        "nancy_brain.article_import.requests.get",
        return_value=MockResponse(
            text=_atom_feed(
                [
                    {
                        "arxiv_id": "1503.03757",
                        "title": "WFIRST-AFTA Report",
                        "author": "David Spergel",
                        "year": "2015",
                        "pdf_url": "http://arxiv.org/pdf/1503.03757v2",
                    }
                ]
            )
        ),
    ) as mock_get:
        summary = import_from_bibtex(bib, "journal_articles", output)

    assert summary["added"] == 1
    assert summary["skipped_duplicate"] == 0
    assert "id_list=1503.03757" in mock_get.call_args[0][0]

    data = yaml.safe_load(output.read_text(encoding="utf-8"))
    item = data["journal_articles"][0]
    assert item["url"] == "https://arxiv.org/pdf/1503.03757.pdf"


def test_bibtex_arxiv_with_prefix(tmp_path):
    bib = tmp_path / "refs.bib"
    _write_bib(
        bib,
        """
@article{spergel2015,
  title={WFIRST report},
  author={Spergel, David N.},
  year={2015},
  eprint={arXiv:1503.03757}
}
""",
    )

    output = tmp_path / "articles.yml"
    with patch(
        "nancy_brain.article_import.requests.get",
        return_value=MockResponse(text=_atom_feed([{"arxiv_id": "1503.03757", "title": "WFIRST report"}])),
    ) as mock_get:
        summary = import_from_bibtex(bib, "journal_articles", output)

    assert summary["added"] == 1
    called_url = mock_get.call_args[0][0]
    assert "id_list=1503.03757" in called_url
    assert "arXiv%3A" not in called_url


def test_bibtex_title_fallback(tmp_path):
    bib = tmp_path / "refs.bib"
    _write_bib(
        bib,
        """
@article{fallback,
  title={Unique Fallback Title},
  author={Jane Doe},
  year={2024}
}
""",
    )
    output = tmp_path / "articles.yml"

    with patch(
        "nancy_brain.article_import.requests.get",
        return_value=MockResponse(
            text=_atom_feed(
                [
                    {
                        "arxiv_id": "2401.01234",
                        "title": "Unique Fallback Title",
                        "author": "Jane Doe",
                        "year": "2024",
                    }
                ]
            )
        ),
    ) as mock_get:
        summary = import_from_bibtex(bib, "journal_articles", output)

    assert summary["added"] == 1
    assert "search_query=" in mock_get.call_args[0][0]

    data = yaml.safe_load(output.read_text(encoding="utf-8"))
    assert data["journal_articles"][0]["url"] == "https://arxiv.org/pdf/2401.01234.pdf"


def test_bibtex_doi_only_entry(tmp_path, caplog):
    bib = tmp_path / "refs.bib"
    _write_bib(
        bib,
        """
@article{doi_only,
  title={Paywalled Journal Article},
  author={Smith, Alice},
  year={2023},
  doi={10.1000/example-doi}
}
""",
    )
    output = tmp_path / "articles.yml"

    with patch(
        "nancy_brain.article_import.requests.get",
        return_value=MockResponse(text=_atom_feed([])),
    ) as mock_get:
        caplog.set_level(logging.WARNING)
        summary = import_from_bibtex(bib, "journal_articles", output)

    assert summary["added"] == 1
    assert mock_get.call_count == 1  # title fallback search
    data = yaml.safe_load(output.read_text(encoding="utf-8"))
    assert data["journal_articles"][0]["url"] == "https://doi.org/10.1000/example-doi"
    assert any("paywalled" in record.message.lower() for record in caplog.records)


def test_bibtex_duplicate_skipped(tmp_path):
    bib = tmp_path / "refs.bib"
    _write_bib(
        bib,
        """
@article{dup,
  title={Duplicate Test},
  author={Spergel, David N.},
  year={2015},
  eprint={1503.03757}
}
""",
    )
    output = tmp_path / "articles.yml"

    with patch(
        "nancy_brain.article_import.requests.get",
        return_value=MockResponse(text=_atom_feed([{"arxiv_id": "1503.03757", "title": "Duplicate Test"}])),
    ):
        first = import_from_bibtex(bib, "journal_articles", output)
        second = import_from_bibtex(bib, "journal_articles", output)

    assert first["added"] == 1
    assert second["added"] == 0
    assert second["skipped_duplicate"] == 1


def test_bibtex_name_sanitization(tmp_path):
    bib = tmp_path / "refs.bib"
    _write_bib(
        bib,
        """
@article{sanitize,
  title={Sanitization Test},
  author={García Márquez, José},
  year={2023},
  doi={10.1000/sanitize-me}
}
""",
    )
    output = tmp_path / "articles.yml"

    with patch("nancy_brain.article_import.requests.get", return_value=MockResponse(text=_atom_feed([]))):
        import_from_bibtex(bib, "journal_articles", output)

    data = yaml.safe_load(output.read_text(encoding="utf-8"))
    name = data["journal_articles"][0]["name"]
    assert re.match(r"^[A-Za-z0-9_]+$", name)
    assert "Garcia" in name


def test_bibtex_creates_yml_if_absent(tmp_path):
    bib = tmp_path / "refs.bib"
    _write_bib(
        bib,
        """
@article{create,
  title={Create Config},
  author={Spergel, David N.},
  year={2015},
  eprint={1503.03757}
}
""",
    )
    output = tmp_path / "new" / "articles.yml"

    with patch(
        "nancy_brain.article_import.requests.get",
        return_value=MockResponse(text=_atom_feed([{"arxiv_id": "1503.03757", "title": "Create Config"}])),
    ):
        summary = import_from_bibtex(bib, "journal_articles", output)

    assert summary["added"] == 1
    assert output.exists()
    data = yaml.safe_load(output.read_text(encoding="utf-8"))
    assert "journal_articles" in data


def test_bibtex_merges_into_existing(tmp_path):
    output = tmp_path / "articles.yml"
    output.write_text(
        """
roman_mission:
  - name: Existing_2020_arXiv_2001_00001
    url: https://arxiv.org/pdf/2001.00001.pdf
    description: Existing item
""",
        encoding="utf-8",
    )
    bib = tmp_path / "refs.bib"
    _write_bib(
        bib,
        """
@article{merge,
  title={Merge Test},
  author={Spergel, David N.},
  year={2015},
  eprint={1503.03757}
}
""",
    )

    with patch(
        "nancy_brain.article_import.requests.get",
        return_value=MockResponse(text=_atom_feed([{"arxiv_id": "1503.03757", "title": "Merge Test"}])),
    ):
        import_from_bibtex(bib, "journal_articles", output)

    data = yaml.safe_load(output.read_text(encoding="utf-8"))
    assert "roman_mission" in data
    assert len(data["roman_mission"]) == 1
    assert len(data["journal_articles"]) == 1


def test_bibtex_dry_run_no_write(tmp_path):
    bib = tmp_path / "refs.bib"
    _write_bib(
        bib,
        """
@article{dryrun,
  title={Dry Run Test},
  author={Spergel, David N.},
  year={2015},
  eprint={1503.03757}
}
""",
    )
    output = tmp_path / "articles.yml"

    with patch(
        "nancy_brain.article_import.requests.get",
        return_value=MockResponse(text=_atom_feed([{"arxiv_id": "1503.03757", "title": "Dry Run Test"}])),
    ):
        summary = import_from_bibtex(bib, "journal_articles", output, dry_run=True)

    assert summary["added"] == 1
    assert not output.exists()


def test_ads_library_lookup(tmp_path, monkeypatch):
    monkeypatch.setenv("ADS_API_KEY", "secret")
    output = tmp_path / "articles.yml"

    get_responses = [
        MockResponse(json_data={"libraries": [{"id": "LIB123", "name": "My ADS Library"}]}),
        MockResponse(json_data={"documents": [], "metadata": {"num_documents": 0}}),
    ]

    with (
        patch("nancy_brain.article_import.requests.get", side_effect=get_responses) as mock_get,
        patch("nancy_brain.article_import.requests.post") as mock_post,
    ):
        summary = import_from_ads("My ADS Library", "journal_articles", output)

    assert summary["added"] == 0
    assert mock_post.call_count == 0
    assert any("/biblib/libraries/LIB123" in call.args[0] for call in mock_get.call_args_list)


def test_ads_library_not_found(tmp_path, monkeypatch):
    monkeypatch.setenv("ADS_API_KEY", "secret")
    output = tmp_path / "articles.yml"

    with patch(
        "nancy_brain.article_import.requests.get",
        return_value=MockResponse(json_data={"libraries": [{"id": "X", "name": "Different"}]}),
    ):
        with pytest.raises(click.ClickException, match="ADS library 'Missing Library' not found"):
            import_from_ads("Missing Library", "journal_articles", output)


def test_ads_bigquery_arxiv(tmp_path, monkeypatch):
    monkeypatch.setenv("ADS_API_KEY", "secret")
    output = tmp_path / "articles.yml"

    get_responses = [
        MockResponse(json_data={"libraries": [{"id": "LIB123", "name": "My ADS Library"}]}),
        MockResponse(json_data={"documents": ["2015arXiv150303757S"], "metadata": {"num_documents": 1}}),
        MockResponse(text=_atom_feed([{"arxiv_id": "1503.03757", "title": "WFIRST-AFTA Report", "year": "2015"}])),
    ]
    post_response = MockResponse(
        json_data={
            "response": {
                "docs": [
                    {
                        "bibcode": "2015arXiv150303757S",
                        "title": ["Old ADS Title"],
                        "author": ["Spergel, David"],
                        "identifier": ["arXiv:1503.03757"],
                        "doi": [],
                        "pubdate": "2015-02-00",
                    }
                ]
            }
        }
    )

    with (
        patch("nancy_brain.article_import.requests.get", side_effect=get_responses) as mock_get,
        patch("nancy_brain.article_import.requests.post", return_value=post_response) as mock_post,
    ):
        summary = import_from_ads("My ADS Library", "journal_articles", output)

    assert summary["added"] == 1
    assert mock_post.call_count == 1
    assert any("id_list=1503.03757" in call.args[0] for call in mock_get.call_args_list)

    data = yaml.safe_load(output.read_text(encoding="utf-8"))
    assert data["journal_articles"][0]["url"] == "https://arxiv.org/pdf/1503.03757.pdf"


def test_ads_bigquery_doi_only(tmp_path, monkeypatch):
    monkeypatch.setenv("ADS_API_KEY", "secret")
    output = tmp_path / "articles.yml"

    get_responses = [
        MockResponse(json_data={"libraries": [{"id": "LIB123", "name": "My ADS Library"}]}),
        MockResponse(json_data={"documents": ["2020ApJ....1..123A"], "metadata": {"num_documents": 1}}),
    ]
    post_response = MockResponse(
        json_data={
            "response": {
                "docs": [
                    {
                        "bibcode": "2020ApJ....1..123A",
                        "title": ["DOI Only Article"],
                        "author": ["Author, Example"],
                        "identifier": ["bibcode:2020ApJ....1..123A"],
                        "doi": ["10.1000/ads-doi"],
                        "pubdate": "2020-01-00",
                    }
                ]
            }
        }
    )

    with (
        patch("nancy_brain.article_import.requests.get", side_effect=get_responses) as mock_get,
        patch("nancy_brain.article_import.requests.post", return_value=post_response),
    ):
        summary = import_from_ads("My ADS Library", "journal_articles", output)

    assert summary["added"] == 1
    assert len(mock_get.call_args_list) == 2  # no arXiv lookup path

    data = yaml.safe_load(output.read_text(encoding="utf-8"))
    assert data["journal_articles"][0]["url"] == "https://doi.org/10.1000/ads-doi"


def test_ads_missing_key(tmp_path, monkeypatch):
    monkeypatch.delenv("ADS_API_KEY", raising=False)
    output = tmp_path / "articles.yml"

    with pytest.raises(click.ClickException, match="ADS_API_KEY environment variable is not set"):
        import_from_ads("Any Library", "journal_articles", output)


def test_bibtex_arxiv_error_feed_skipped(tmp_path):
    """Entry with an invalid arxiv_id is skipped rather than added with a broken URL."""
    bib_file = tmp_path / "refs.bib"
    output = tmp_path / "articles.yml"
    _write_bib(
        bib_file,
        """
@article{bogus2024,
  archivePrefix = {arXiv},
  eprint        = {not-a-real-id},
  title         = {Bogus Article},
  author        = {Author, Test},
  year          = {2024}
}
""",
    )

    error_feed = (
        "<?xml version='1.0' encoding='UTF-8'?>\n"
        "<feed xmlns='http://www.w3.org/2005/Atom'>\n"
        "  <entry>\n"
        "    <id>http://arxiv.org/api/errors#incorrect_id_format</id>\n"
        "    <title>Error</title>\n"
        "    <summary>incorrect id format for not-a-real-id</summary>\n"
        "  </entry>\n"
        "</feed>"
    )

    with patch(
        "nancy_brain.article_import.requests.get",
        return_value=MockResponse(text=error_feed),
    ):
        summary = import_from_bibtex(bib_file, "papers", output)

    assert summary["added"] == 0
    assert summary["skipped_no_url"] == 1


# ---------------------------------------------------------------------------
# Additional tests for helper functions to improve coverage
# ---------------------------------------------------------------------------

from nancy_brain.article_import import (
    _sanitize,
    _make_name,
    _chunks,
    _dedupe_preserve_order,
    _normalize_arxiv_id,
    _looks_like_arxiv_id,
    _first_author_surname,
    _extract_year,
    _clean_text,
    _normalize_title_for_compare,
    _build_description,
)


def test_sanitize_empty():
    assert _sanitize("") == ""


def test_sanitize_basic():
    assert _sanitize("Hello World!") == "Hello_World"


def test_make_name_no_arxiv_no_doi():
    name = _make_name("Smith", "2023")
    assert "Smith" in name
    assert "2023" in name


def test_make_name_long_name():
    # Name longer than 80 chars should be truncated
    name = _make_name("A" * 50, "2023")
    assert len(name) <= 80


def test_make_name_with_doi():
    name = _make_name("Jones", "2021", doi="10.1000/xyz123")
    assert "Jones" in name
    assert "2021" in name


def test_chunks_basic():
    result = _chunks([1, 2, 3, 4, 5], 2)
    assert result == [[1, 2], [3, 4], [5]]


def test_dedupe_preserve_order_with_dupes():
    result = _dedupe_preserve_order(["a", "b", "a", "c"])
    assert result == ["a", "b", "c"]


def test_normalize_arxiv_id_none():
    assert _normalize_arxiv_id(None) is None
    assert _normalize_arxiv_id("") is None


def test_normalize_arxiv_id_url():
    result = _normalize_arxiv_id("https://arxiv.org/abs/2301.00001v2")
    assert result == "2301.00001"


def test_looks_like_arxiv_id_none():
    assert _looks_like_arxiv_id(None) is False
    assert _looks_like_arxiv_id("") is False


def test_looks_like_arxiv_id_arxiv_prefix():
    assert _looks_like_arxiv_id("arxiv:2301.00001") is True


def test_looks_like_arxiv_id_url():
    assert _looks_like_arxiv_id("https://arxiv.org/abs/2301.00001") is True


def test_looks_like_arxiv_id_numeric():
    assert _looks_like_arxiv_id("2301.00001") is True


def test_looks_like_arxiv_id_old_style():
    assert _looks_like_arxiv_id("astro-ph/9912345") is True


def test_first_author_surname_none():
    assert _first_author_surname(None) == "Unknown"


def test_first_author_surname_comma_format():
    assert _first_author_surname("Smith, John") == "Smith"


def test_first_author_surname_space_format():
    assert _first_author_surname("John Smith") == "Smith"


def test_first_author_surname_multiple_authors():
    assert _first_author_surname("Smith, John and Jones, Jane") == "Smith"


def test_extract_year_none():
    assert _extract_year(None) == "Unknown"


def test_extract_year_no_year():
    assert _extract_year("no year here") == "Unknown"


def test_extract_year_valid():
    assert _extract_year("Published in 2021") == "2021"


def test_clean_text_none():
    assert _clean_text(None) == ""


def test_clean_text_basic():
    result = _clean_text("{Hello} {World}")
    assert "Hello" in result
    assert "World" in result
    assert "{" not in result


def test_normalize_title_for_compare_none():
    assert _normalize_title_for_compare(None) == ""


def test_normalize_title_for_compare_basic():
    result = _normalize_title_for_compare("Hello, World! 2023")
    assert result == "helloworld2023"


def test_build_description_full():
    result = _build_description("Great Paper", "Smith", "2023")
    assert "Smith" in result
    assert "2023" in result
    assert "Great Paper" in result


def test_build_description_no_year():
    result = _build_description("Great Paper", "Smith", "no year")
    assert "Great Paper" in result
    assert "Smith" in result


def test_build_description_no_title():
    result = _build_description("", "Smith", "2023")
    assert "Smith" in result
    assert "2023" in result


# ---------------------------------------------------------------------------
# Additional tests for better coverage on helper functions
# ---------------------------------------------------------------------------

from nancy_brain.article_import import (
    _first_list_item,
    _entry_arxiv_id,
    _load_articles_yaml,
    _merge_entries,
    arxiv_lookup,
    _arxiv_title_search,
    _parse_arxiv_atom,
    _write_articles_yaml,
)


def test_first_list_item_list():
    assert _first_list_item(["first", "second"]) == "first"


def test_first_list_item_string():
    assert _first_list_item("hello") == "hello"


def test_first_list_item_other():
    assert _first_list_item(42) == ""
    assert _first_list_item([]) == ""


def test_entry_arxiv_id_url():
    entry = {"url": "https://arxiv.org/abs/2301.00001"}
    result = _entry_arxiv_id(entry)
    assert result == "2301.00001"


def test_entry_arxiv_id_eprint_arxiv():
    entry = {"eprint": "2301.00001", "archiveprefix": "arXiv"}
    result = _entry_arxiv_id(entry)
    assert result == "2301.00001"


def test_entry_arxiv_id_none():
    entry = {"title": "No ID here"}
    assert _entry_arxiv_id(entry) is None


def test_load_articles_yaml_invalid_structure(tmp_path):
    """Invalid YAML structure (list instead of dict) raises ClickException."""
    yaml_file = tmp_path / "articles.yml"
    yaml_file.write_text("- item1\n- item2\n", encoding="utf-8")

    with pytest.raises(click.ClickException):
        _load_articles_yaml(yaml_file)


def test_merge_entries_invalid_category():
    """Non-list category raises ClickException."""
    data = {"papers": "not-a-list"}
    with pytest.raises(click.ClickException):
        _merge_entries(data, "papers", [])


def test_merge_entries_entry_without_name():
    """Entry without name is counted as duplicate and skipped."""
    data = {}
    entries = [{"url": "https://arxiv.org/pdf/2301.00001.pdf"}]  # no 'name' key
    added, skipped = _merge_entries(data, "papers", entries)
    assert added == 0
    assert skipped == 1


def test_arxiv_lookup_empty():
    """Empty input returns empty list without making API calls."""
    result = arxiv_lookup([])
    assert result == []


def test_arxiv_title_search_empty():
    """Empty title returns None without making API calls."""
    result = _arxiv_title_search("")
    assert result is None


def test_parse_arxiv_atom_error_entry():
    """Error-feed entries (title='Error') are skipped."""
    xml = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/2301.00001v1</id>
    <title>Error</title>
    <published>2023-01-01T00:00:00Z</published>
  </entry>
</feed>"""
    results = _parse_arxiv_atom(xml)
    assert results == []


def test_write_articles_yaml(tmp_path):
    """_write_articles_yaml creates directory and writes YAML file."""
    output_path = tmp_path / "subdir" / "articles.yml"
    data = {"papers": [{"name": "test", "url": "https://example.com"}]}
    _write_articles_yaml(output_path, data)
    assert output_path.exists()
    import yaml

    loaded = yaml.safe_load(output_path.read_text())
    assert "papers" in loaded


def test_import_from_bibtex_missing_file(tmp_path):
    """import_from_bibtex raises ClickException for missing file."""
    with pytest.raises(click.ClickException):
        import_from_bibtex(
            bib_path=tmp_path / "nonexistent.bib",
            category="papers",
            output_path=tmp_path / "articles.yml",
        )


def test_import_from_ads_no_key(tmp_path, monkeypatch):
    """import_from_ads raises ClickException when ADS_API_KEY is not set."""
    monkeypatch.delenv("ADS_API_KEY", raising=False)
    with pytest.raises(click.ClickException, match="ADS_API_KEY"):
        import_from_ads(
            library_name="My Library",
            category="papers",
            output_path=tmp_path / "articles.yml",
        )
