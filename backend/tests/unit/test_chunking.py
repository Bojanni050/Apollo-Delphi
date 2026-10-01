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


def _lines(text, chunk_size=500, overlap=0):
    return [(c.line_start, c.line_end) for c in Chunker(chunk_size=chunk_size, overlap=overlap).chunk(_extraction(text))]


def test_line_range_of_a_single_chunk():
    assert _lines("one\ntwo\nthree") == [(1, 3)]


def test_line_range_ignores_surrounding_blank_lines():
    assert _lines("\n\nfirst\nsecond\n\n") == [(3, 4)]


def test_line_ranges_follow_sections():
    text = "# Intro\nalpha\nbeta\n\n# Results\ngamma"
    assert _lines(text) == [(1, 3), (5, 6)]


def test_line_ranges_of_sliding_windows_cover_their_own_text():
    text = "\n".join(f"line {i:02d}" for i in range(1, 21))  # 20 lines of 7 chars
    extraction = _extraction(text)
    source = text.split("\n")
    chunks = Chunker(chunk_size=40, overlap=10).chunk(extraction)
    assert len(chunks) > 2
    for c in chunks:
        covered = "\n".join(source[c.line_start - 1 : c.line_end])
        assert c.content.strip() in covered, (c.line_start, c.line_end)
        assert c.line_start <= c.line_end
    assert chunks[0].line_start == 1 and chunks[-1].line_end == 20


def test_line_range_with_leading_text_before_first_heading():
    text = "preamble\n\n# Heading\nbody"
    assert _lines(text) == [(1, 1), (3, 4)]
