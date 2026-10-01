"""The text of a document for the reading pane: the extracted text, where its pages start and where its fragments lie.

The reading pane shows the same text the indexer read, with line numbers, so a citation ("lines 28-36") and a search hit
can be shown in place. Line numbers refer to this extracted text, as they do on the chunks.
"""
from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass, field

from app.models import Document
from app.services.extraction.base import ExtractionResult

#: A document longer than this is cut (and flagged); the pane is for reading, not for megabytes of digest.
MAX_CHARS = 3_000_000
_CACHE_SIZE = 8
_cache: OrderedDict[tuple[int, str], "ReadableText"] = OrderedDict()


@dataclass
class PageStart:
    page_number: int
    line: int


@dataclass
class ReadableText:
    text: str
    line_count: int
    pages: list[PageStart] = field(default_factory=list)
    truncated: bool = False


def readable_text(extraction: ExtractionResult) -> ReadableText:
    """The extracted text with the line where each page starts (pages are joined with a blank line, as the extractor does)."""
    text = extraction.full_text
    truncated = len(text) > MAX_CHARS
    if truncated:
        text = text[:MAX_CHARS]
    pages: list[PageStart] = []
    if extraction.pages and any(p.page_number is not None for p in extraction.pages):
        cursor = 0
        for page in extraction.pages:
            if page.page_number is not None and cursor <= len(text):
                pages.append(PageStart(page.page_number, text.count("\n", 0, cursor) + 1))
            cursor += len(page.text) + 2
    return ReadableText(text=text, line_count=text.count("\n") + 1 if text else 0, pages=pages, truncated=truncated)


def cached_text(doc: Document, load) -> ReadableText:
    """Extraction (a PDF in particular) is slow and the pane asks again for every citation: remember the last few."""
    key = (doc.id, doc.content_hash)
    if key in _cache:
        _cache.move_to_end(key)
        return _cache[key]
    value = readable_text(load(doc))
    _cache[key] = value
    while len(_cache) > _CACHE_SIZE:
        _cache.popitem(last=False)
    return value
