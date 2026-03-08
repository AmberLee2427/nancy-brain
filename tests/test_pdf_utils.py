"""Tests for scripts/pdf_utils.py - PDF extraction utilities."""

import pytest
from unittest.mock import patch, MagicMock


def test_initialize_tika_success():
    """initialize_tika returns True when tika is available."""
    import types

    fake_tika = types.SimpleNamespace(initVM=MagicMock())
    with patch.dict("sys.modules", {"tika": fake_tika}):
        from scripts import pdf_utils

        with patch("scripts.pdf_utils.initialize_tika", wraps=None) as mock_fn:
            mock_fn.return_value = True
            result = mock_fn()
    assert result is True


def test_initialize_tika_failure():
    """initialize_tika returns False when tika import/init fails."""
    import importlib
    import sys

    # Mock a tika module that raises on initVM
    import types

    fake_tika = types.SimpleNamespace(initVM=MagicMock(side_effect=RuntimeError("tika failed")))

    saved = sys.modules.get("tika")
    sys.modules["tika"] = fake_tika

    try:
        # Re-import to pick up the mocked module
        import scripts.pdf_utils as pdf_utils
        result = pdf_utils.initialize_tika()
        assert result is False
    finally:
        if saved is None:
            sys.modules.pop("tika", None)
        else:
            sys.modules["tika"] = saved


def test_extract_pdf_text_success(tmp_path):
    """extract_pdf_text returns text when tika parser succeeds."""
    from scripts.pdf_utils import extract_pdf_text

    dummy_content = "Extracted PDF text content."
    mock_parsed = {"content": dummy_content}

    import types
    fake_parser = types.SimpleNamespace(from_file=MagicMock(return_value=mock_parsed))
    fake_tika_module = types.SimpleNamespace(parser=fake_parser)

    with patch.dict("sys.modules", {"tika": fake_tika_module, "tika.parser": fake_parser}):
        with patch("scripts.pdf_utils.extract_pdf_text", return_value=dummy_content) as mock_extract:
            result = mock_extract(str(tmp_path / "test.pdf"))
    assert result == dummy_content


def test_extract_pdf_text_no_content(tmp_path):
    """extract_pdf_text returns None when parsed content is empty."""
    from scripts.pdf_utils import extract_pdf_text

    with patch("scripts.pdf_utils.extract_pdf_text", return_value=None) as mock_extract:
        result = mock_extract(str(tmp_path / "empty.pdf"))
    assert result is None


def test_test_pdf_extraction_missing_file(tmp_path):
    """test_pdf_extraction returns False when file does not exist."""
    from scripts.pdf_utils import test_pdf_extraction

    result = test_pdf_extraction(str(tmp_path / "missing.pdf"))
    assert result is False


def test_test_pdf_extraction_tika_init_fails(tmp_path):
    """test_pdf_extraction returns False when Tika VM cannot be initialised."""
    pdf_path = tmp_path / "test.pdf"
    pdf_path.write_bytes(b"fake pdf")

    from scripts import pdf_utils

    with patch("scripts.pdf_utils.initialize_tika", return_value=False):
        result = pdf_utils.test_pdf_extraction(str(pdf_path))
    assert result is False


def test_test_pdf_extraction_success(tmp_path):
    """test_pdf_extraction returns True when extraction succeeds."""
    pdf_path = tmp_path / "real.pdf"
    pdf_path.write_bytes(b"fake pdf")

    from scripts import pdf_utils

    with patch("scripts.pdf_utils.initialize_tika", return_value=True):
        with patch("scripts.pdf_utils.extract_pdf_text", return_value="Some text content"):
            result = pdf_utils.test_pdf_extraction(str(pdf_path))
    assert result is True


def test_test_pdf_extraction_extract_fails(tmp_path):
    """test_pdf_extraction returns False when extract_pdf_text returns None."""
    pdf_path = tmp_path / "empty.pdf"
    pdf_path.write_bytes(b"fake pdf")

    from scripts import pdf_utils

    with patch("scripts.pdf_utils.initialize_tika", return_value=True):
        with patch("scripts.pdf_utils.extract_pdf_text", return_value=None):
            result = pdf_utils.test_pdf_extraction(str(pdf_path))
    assert result is False


# ---------------------------------------------------------------------------
# Additional tests to improve line coverage
# ---------------------------------------------------------------------------

import types
import sys


def test_initialize_tika_actually_succeeds():
    """Test the actual initialize_tika function by mocking tika."""
    fake_tika = types.SimpleNamespace(initVM=MagicMock())
    saved = sys.modules.get("tika")
    sys.modules["tika"] = fake_tika

    try:
        import importlib
        import scripts.pdf_utils as pdf_mod
        importlib.reload(pdf_mod)
        result = pdf_mod.initialize_tika()
        assert result is True
        fake_tika.initVM.assert_called_once()
    finally:
        if saved is None:
            sys.modules.pop("tika", None)
        else:
            sys.modules["tika"] = saved


def test_initialize_tika_actually_fails():
    """Test the actual initialize_tika function when initVM raises."""
    fake_tika = types.SimpleNamespace(initVM=MagicMock(side_effect=RuntimeError("vm error")))
    saved = sys.modules.get("tika")
    sys.modules["tika"] = fake_tika

    try:
        import scripts.pdf_utils as pdf_mod
        result = pdf_mod.initialize_tika()
        assert result is False
    finally:
        if saved is None:
            sys.modules.pop("tika", None)
        else:
            sys.modules["tika"] = saved


def test_extract_pdf_text_actually_succeeds():
    """Test the actual extract_pdf_text function with mocked tika.parser."""
    fake_parser_obj = MagicMock()
    fake_parser_obj.from_file.return_value = {"content": "Extracted content"}
    fake_tika_parser_module = types.ModuleType("tika.parser")
    fake_tika_parser_module.from_file = fake_parser_obj.from_file
    fake_tika_module = types.ModuleType("tika")

    saved_tika = sys.modules.get("tika")
    saved_tika_parser = sys.modules.get("tika.parser")
    sys.modules["tika"] = fake_tika_module
    sys.modules["tika.parser"] = fake_tika_parser_module

    try:
        import scripts.pdf_utils as pdf_mod
        result = pdf_mod.extract_pdf_text("/tmp/test.pdf")
        assert result == "Extracted content"
    finally:
        if saved_tika is None:
            sys.modules.pop("tika", None)
        else:
            sys.modules["tika"] = saved_tika
        if saved_tika_parser is None:
            sys.modules.pop("tika.parser", None)
        else:
            sys.modules["tika.parser"] = saved_tika_parser


def test_extract_pdf_text_empty_content():
    """Test extract_pdf_text when content is empty."""
    fake_parser_obj = MagicMock()
    fake_parser_obj.from_file.return_value = {"content": None}
    fake_tika_parser_module = types.ModuleType("tika.parser")
    fake_tika_parser_module.from_file = fake_parser_obj.from_file
    fake_tika_module = types.ModuleType("tika")

    saved_tika = sys.modules.get("tika")
    saved_tika_parser = sys.modules.get("tika.parser")
    sys.modules["tika"] = fake_tika_module
    sys.modules["tika.parser"] = fake_tika_parser_module

    try:
        import scripts.pdf_utils as pdf_mod
        result = pdf_mod.extract_pdf_text("/tmp/empty.pdf")
        assert result is None
    finally:
        if saved_tika is None:
            sys.modules.pop("tika", None)
        else:
            sys.modules["tika"] = saved_tika
        if saved_tika_parser is None:
            sys.modules.pop("tika.parser", None)
        else:
            sys.modules["tika.parser"] = saved_tika_parser


def test_extract_pdf_text_exception():
    """Test extract_pdf_text when tika raises an exception."""
    fake_parser_obj = MagicMock()
    fake_parser_obj.from_file.side_effect = Exception("tika error")
    fake_tika_parser_module = types.ModuleType("tika.parser")
    fake_tika_parser_module.from_file = fake_parser_obj.from_file
    fake_tika_module = types.ModuleType("tika")

    saved_tika = sys.modules.get("tika")
    saved_tika_parser = sys.modules.get("tika.parser")
    sys.modules["tika"] = fake_tika_module
    sys.modules["tika.parser"] = fake_tika_parser_module

    try:
        import scripts.pdf_utils as pdf_mod
        result = pdf_mod.extract_pdf_text("/tmp/broken.pdf")
        assert result is None
    finally:
        if saved_tika is None:
            sys.modules.pop("tika", None)
        else:
            sys.modules["tika"] = saved_tika
        if saved_tika_parser is None:
            sys.modules.pop("tika.parser", None)
        else:
            sys.modules["tika.parser"] = saved_tika_parser
