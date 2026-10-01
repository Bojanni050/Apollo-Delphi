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
    #: 1-based, inclusive line range of the chunk in the extracted text (the first line that holds
    #: text to the last one). For txt/md that is the file's own numbering.
    line_start: int | None = None
    line_end: int | None = None


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

    def _sliding_windows(self, text: str) -> list[tuple[int, str]]:
        """(start offset within the stripped text, window) pairs."""
        text = text.strip()
        if len(text) <= self.chunk_size:
            return [(0, text)] if text else []
        step = max(1, self.chunk_size - self.overlap)
        windows: list[tuple[int, str]] = []
        start = 0
        while start < len(text):
            window = text[start : start + self.chunk_size]
            if windows and window == windows[-1][1]:
                break
            windows.append((start, window))
            if start + self.chunk_size >= len(text):
                break
            start += step
        return windows

    @staticmethod
    def _line_range(full_text: str, start: int, window: str) -> tuple[int, int] | None:
        """Lines holding the window's text; ``start`` is the window's offset in ``full_text``."""
        body = window.strip()
        if not body:
            return None
        first = start + len(window) - len(window.lstrip())
        line_start = full_text.count("\n", 0, first) + 1
        return line_start, line_start + body.count("\n")

    def chunk(self, extraction: ExtractionResult) -> list[Chunk]:
        chunks: list[Chunk] = []
        offset = 0
        for heading, block in _split_into_blocks(extraction.full_text):
            windows = self._sliding_windows(block)
            if not windows:
                offset += len(block)
                continue
            lead = len(block) - len(block.lstrip())  # _sliding_windows works on the stripped block
            window_start = 0
            for start, w in windows:
                page_number = self._page_number(extraction, offset + window_start)
                lines = self._line_range(extraction.full_text, offset + lead + start, w)
                chunks.append(
                    Chunk(
                        chunk_index=len(chunks),
                        content=w,
                        page_number=page_number,
                        section=heading,
                        line_start=lines[0] if lines else None,
                        line_end=lines[1] if lines else None,
                    )
                )
                window_start += max(1, self.chunk_size - self.overlap)
            offset += len(block)
        if not chunks and extraction.full_text.strip():
            full = extraction.full_text
            lines = self._line_range(full, 0, full)
            chunks.append(
                Chunk(
                    chunk_index=0, content=full.strip(), page_number=None, section=None,
                    line_start=lines[0], line_end=lines[1],
                )
            )
        return chunks
