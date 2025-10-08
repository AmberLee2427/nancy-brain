from pathlib import Path

from chunky import ChunkPipeline, ChunkerConfig, Document

from nancy_brain.chunking import strip_chunk_suffix


def _make_content(lines: int) -> str:
    return "\n".join(f"line {i}" for i in range(1, lines + 1))


def test_pipeline_respects_line_window(tmp_path: Path) -> None:
    pipeline = ChunkPipeline()
    lines_per_chunk = 40
    line_overlap = 5
    config = ChunkerConfig(lines_per_chunk=lines_per_chunk, line_overlap=line_overlap)

    path = tmp_path / "sample.py"
    path.write_text(_make_content(120), encoding="utf-8")

    doc_id = "cat/repo/sample.py"
    document = Document(path=path, content=path.read_text(), metadata={"doc_id": doc_id})
    chunks = pipeline.chunk_documents([document], config=config)

    step = max(1, lines_per_chunk - line_overlap)
    total_lines = 120
    expected = 1 if total_lines <= lines_per_chunk else ((total_lines - lines_per_chunk + step - 1) // step) + 1

    assert len(chunks) == expected
    assert chunks[0].chunk_id == f"{doc_id}#chunk-0000"
    assert chunks[0].metadata["line_start"] == 1
    assert chunks[0].metadata["line_end"] == lines_per_chunk
    for previous, current in zip(chunks, chunks[1:]):
        assert current.metadata["line_start"] == previous.metadata["line_end"] - line_overlap + 1
        assert previous.metadata["chunk_count"] == expected
        assert current.metadata["chunk_count"] == expected
        assert previous.metadata["source_document"] == doc_id
        assert current.metadata["source_document"] == doc_id
    assert chunks[-1].metadata["line_end"] == total_lines


def test_pipeline_handles_empty_files(tmp_path: Path) -> None:
    pipeline = ChunkPipeline()
    path = tmp_path / "empty.txt"
    path.write_text("", encoding="utf-8")

    document = Document(path=path, content="", metadata={"doc_id": "docs/empty.txt"})
    chunks = pipeline.chunk_documents([document])

    assert len(chunks) == 1
    chunk = chunks[0]
    assert chunk.chunk_id == "docs/empty.txt#chunk-0000"
    assert chunk.text == ""
    assert chunk.metadata["line_start"] == 0
    assert chunk.metadata["line_end"] == 0
    assert chunk.metadata["chunk_count"] == 1


def test_strip_chunk_suffix():
    cases = [
        ("pkg/module.py#chunk-0002", "pkg/module.py"),
        ("pkg/module.py::chunk-0002", "pkg/module.py"),
        ("pkg/module.py|chunk:3", "pkg/module.py"),
        ("pkg/module.py", "pkg/module.py"),
    ]
    for doc_id, expected in cases:
        assert strip_chunk_suffix(doc_id) == expected
