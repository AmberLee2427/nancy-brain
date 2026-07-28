import pytest  # noqa: F401 E0401
import json
import sqlite3

from rag_core.store import Store


def test_read_lines_full_and_range(tmp_path):
    # Create a sample text file
    doc_id = "sample"
    lines = ["first line\n", "second line\n", "third line\n"]
    file_path = tmp_path / f"{doc_id}.txt"
    file_path.write_text("".join(lines))

    store = Store(tmp_path)
    # Full read
    full = store.read_lines(doc_id)
    assert full == "".join(lines)

    # Range read
    sub = store.read_lines(doc_id, start=1, end=3)
    assert sub == "second line\nthird line\n"

    # Out-of-bounds end should not error
    assert store.read_lines(doc_id, start=2, end=10) == "third line\n"

    # Non-existent document
    with pytest.raises(FileNotFoundError):
        store.read_lines("missing_doc")


def test_read_lines_reconstructs_document_from_index(tmp_path):
    index_dir = tmp_path / "embeddings" / "index"
    index_dir.mkdir(parents=True)
    conn = sqlite3.connect(index_dir / "documents")
    try:
        conn.execute(
            """
            CREATE TABLE sections (
                indexid INTEGER PRIMARY KEY AUTOINCREMENT,
                id TEXT,
                text TEXT,
                tags TEXT,
                entry DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        doc_id = "category/repo/README.md"
        chunks = [
            ("first line\nsecond line", 0, 0, 22),
            ("third line\n", 1, 23, 34),
        ]
        for text, chunk_index, span_start, span_end in chunks:
            tags = {
                "source_document": doc_id,
                "chunk_index": chunk_index,
                "span_start": span_start,
                "span_end": span_end,
            }
            conn.execute(
                "INSERT INTO sections (id, text, tags) VALUES (?, ?, ?)",
                (f"{doc_id}#chunk-{chunk_index:04d}", text, json.dumps(tags)),
            )
        conn.commit()
    finally:
        conn.close()

    store = Store(tmp_path)

    assert store.read_lines(doc_id) == "first line\nsecond line\nthird line\n"
    assert store.read_lines(doc_id, start=1, end=3) == "second line\nthird line\n"


def test_read_lines_prefers_source_file_over_index(tmp_path):
    doc_id = "category/repo/README.md"
    source_path = tmp_path / doc_id
    source_path.parent.mkdir(parents=True)
    source_path.write_text("source file\n")

    index_dir = tmp_path / "embeddings" / "index"
    index_dir.mkdir(parents=True)
    conn = sqlite3.connect(index_dir / "documents")
    try:
        conn.execute("CREATE TABLE sections (id TEXT, text TEXT, tags TEXT)")
        conn.execute(
            "INSERT INTO sections VALUES (?, ?, ?)",
            (
                f"{doc_id}#chunk-0000",
                "indexed fallback",
                json.dumps({"source_document": doc_id, "chunk_index": 0}),
            ),
        )
        conn.commit()
    finally:
        conn.close()

    assert Store(tmp_path).read_lines(doc_id) == "source file\n"
