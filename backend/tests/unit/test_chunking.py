from app.services.chunking.chunker import Chunker
from app.services.extraction.base import ExtractionResult, ExtractedPage


def _extraction(text, pages=None):
    return ExtractionResult(pages=pages or [ExtractedPage(None, text)], full_text=text)


def test_small_text_single_chunk():
    chunks = Chunker(chunk_size=100, overlap=10).chunk(_extraction("short text"))
    assert len(chunks) == 1
    assert chunks[0].content == "short text"


def test_long_text_sliding_windows():
    text = " ".join(f"word{i}" for i in range(100))
    chunks = Chunker(chunk_size=200, overlap=50).chunk(_extraction(text))
    assert len(chunks) > 1
    for c in chunks:
        assert len(c.content) <= 200


def test_section_headings_tracked():
    text = "# Intro\n\nAlpha body here.\n\n# Results\n\nBeta body here."
    chunks = Chunker(chunk_size=500, overlap=0).chunk(_extraction(text))
    sections = {c.section for c in chunks}
    assert "Intro" in sections
    assert "Results" in sections


def test_page_numbers_propagated():
    pages = [ExtractedPage(1, "page one text"), ExtractedPage(2, "page two text")]
    extraction = ExtractionResult(pages=pages, full_text="page one text\n\npage two text")
    chunks = Chunker(chunk_size=20, overlap=0).chunk(extraction)
    assert any(c.page_number == 2 for c in chunks)
