import pytest

from nancy_brain.chunking import SmartChunker, strip_chunk_suffix


def test_chunker_splits_long_markdown():
    chunker = SmartChunker(text_chunk_chars=120, text_overlap_chars=20)
    paragraph = "Lorem ipsum dolor sit amet, consectetur adipiscing elit. "
    content = "# Title\n\n" + (paragraph * 20)

    chunks = chunker.chunk("docs/README.md", content)

    assert len(chunks) >= 2
    assert chunks[0].chunk_id.endswith("#chunk-0000")
    assert chunks[0].metadata["chunk_index"] == 0
    assert chunks[0].metadata["source_document"] == "docs/README.md"
    assert all(chunk.metadata["chunk_count"] == len(chunks) for chunk in chunks)


@pytest.mark.parametrize(
    "doc_id",
    [
        "pkg/module.py#chunk-0002",
        "pkg/module.py::chunk-0002",
        "pkg/module.py|chunk:3",
    ],
)
def test_strip_chunk_suffix(doc_id):
    assert strip_chunk_suffix(doc_id) == "pkg/module.py"


def test_chunker_skips_empty_init():
    chunker = SmartChunker()
    content = "# generated file\n__all__ = []\n"

    chunks = chunker.chunk("pkg/__init__.py", content)

    assert chunks == []


def test_chunker_code_chunks_overlap():
    chunker = SmartChunker(code_chunk_lines=6, code_overlap_lines=2)
    code = """
from typing import Any


def foo():
    return 1


def bar(x):
    if x:
        return foo()
    return None


def baz(y):
    return bar(y)
""".strip()

    chunks = chunker.chunk("pkg/sample.py", code)

    assert len(chunks) >= 2
    assert chunks[0].metadata["line_start"] == 1
    assert chunks[0].metadata["line_end"] >= chunks[0].metadata["line_start"]
    assert chunks[1].metadata["line_start"] <= chunks[0].metadata["line_end"]


def test_chunker_skips_tiny_docs_with_few_words():
    chunker = SmartChunker(min_index_chars=80)
    tiny = "todo"
    assert chunker.chunk("docs/todo.txt", tiny) == []


def test_chunker_keeps_short_docs_with_enough_words():
    chunker = SmartChunker(min_index_chars=80)
    content = "one two three four"  # four words, should be kept
    chunks = chunker.chunk("docs/short.txt", content)
    assert len(chunks) == 1
    assert chunks[0].text == content
