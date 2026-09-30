from __future__ import annotations

import re
from dataclasses import dataclass

from app.core.config import get_settings
from app.services.extraction.base import ExtractionResult


@dataclass
class Chunk:
    chunk_index: int
    content: str
    page_number: int | None
    section: str | None


def _split_into_blocks(text: str) -> list[tuple[str | None, str]]:
    """Split text into (heading, body) blocks based on markdown-ish headings."""
    heading_re = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)
    blocks: list[tuple[str | None, str]] = []
    matches = list(heading_re.finditer(text))
    if not matches:
        return [(None, text)]
    if matches[0].start() > 0:
        blocks.append((None, text[: matches[0].start()]))
    for i, m in enumerate(matches):
        section = m.group(2).strip()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[m.start() : end]
        blocks.append((section, body))
    return blocks


class Chunker:
    def __init__(self, chunk_size: int | None = None, overlap: int | None = None):
        settings = get_settings()
        self.chunk_size = chunk_size or settings.chunk_size_chars
        self.overlap = overlap if overlap is not None else settings.chunk_overlap_chars

    def _page_number(self, extraction: ExtractionResult, start: int) -> int | None:
        if not extraction.pages or all(p.page_number is None for p in extraction.pages):
            return None
        return extraction.page_for_offset(start)

    def _sliding_windows(self, text: str) -> list[str]:
        text = text.strip()
        if len(text) <= self.chunk_size:
            return [text] if text else []
        step = max(1, self.chunk_size - self.overlap)
        windows = []
        start = 0
        while start < len(text):
            window = text[start : start + self.chunk_size]
            if windows and window == windows[-1]:
                break
            windows.append(window)
            if start + self.chunk_size >= len(text):
                break
            start += step
        return windows

    def chunk(self, extraction: ExtractionResult) -> list[Chunk]:
        chunks: list[Chunk] = []
        offset = 0
        for heading, block in _split_into_blocks(extraction.full_text):
            windows = self._sliding_windows(block)
            if not windows:
                offset += len(block)
                continue
            window_start = 0
            for w in windows:
                page_number = self._page_number(extraction, offset + window_start)
                chunks.append(
                    Chunk(chunk_index=len(chunks), content=w, page_number=page_number, section=heading)
                )
                window_start += max(1, self.chunk_size - self.overlap)
            offset += len(block)
        if not chunks and extraction.full_text.strip():
            chunks.append(
                Chunk(chunk_index=0, content=extraction.full_text.strip(), page_number=None, section=None)
            )
        return chunks
