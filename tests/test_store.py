import pytest  # noqa: F401 E0401
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
