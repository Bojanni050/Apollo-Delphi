from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class ExtractedPage:
    page_number: int | None
    text: str


@dataclass
class ExtractionResult:
    pages: list[ExtractedPage] = field(default_factory=list)
    full_text: str = ""
    title: str | None = None
    metadata: dict = field(default_factory=dict)

    def page_for_offset(self, offset: int) -> int | None:
        if not self.pages:
            return None
        consumed = 0
        for page in self.pages:
            consumed += len(page.text)
            if offset < consumed:
                return page.page_number
        return self.pages[-1].page_number


class DocumentExtractor(ABC):
    """Abstraction for format-specific text extraction.

    Adding a new format means adding a new subclass and registering it in
    ``get_extractor``; the rest of the pipeline is format agnostic.
    """

    file_type: str = ""

    @abstractmethod
    def extract(self, data: bytes, filename: str) -> ExtractionResult:
        ...


class ExtractionError(Exception):
    pass


def normalize_text(text: str) -> str:
    import re
    import unicodedata

    text = unicodedata.normalize("NFC", text)
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\x00", "")
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{4,}", "\n\n\n", text)
    return text.strip()
