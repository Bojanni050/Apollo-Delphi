from app.services.extraction.base import ExtractionResult, ExtractedPage, normalize_text
from app.services.extraction.extractors import (
    DocxExtractor,
    MarkdownExtractor,
    TextExtractor,
    get_extractor,
)
import pytest

from app.services.extraction.base import ExtractionError


def test_text_extractor():
    result = TextExtractor().extract("Hello\r\nworld".encode(), "a.txt")
    assert result.full_text == "Hello\nworld"
    assert result.pages[0].page_number is None


def test_markdown_extractor_normalizes():
    result = MarkdownExtractor().extract(b"# Title\n\nBody text", "a.md")
    assert "Title" in result.full_text


def test_normalization_strips_weird_chars():
    assert normalize_text("a\x00b\r\nc") == "ab\nc"


def test_get_extractor_unknown_type():
    with pytest.raises(ExtractionError):
        get_extractor("exe")


def test_docx_extractor_invalid_bytes():
    with pytest.raises(ExtractionError):
        DocxExtractor().extract(b"not a docx", "a.docx")
