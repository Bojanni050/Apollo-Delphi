from __future__ import annotations

import io

from .base import DocumentExtractor, ExtractionError, ExtractionResult, ExtractedPage, normalize_text


class TextExtractor(DocumentExtractor):
    file_type = "txt"

    def extract(self, data: bytes, filename: str) -> ExtractionResult:
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ExtractionError("File is not valid UTF-8 text") from exc
        text = normalize_text(text)
        return ExtractionResult(pages=[ExtractedPage(None, text)], full_text=text)


class MarkdownExtractor(TextExtractor):
    file_type = "md"


class PDFExtractor(DocumentExtractor):
    file_type = "pdf"

    def extract(self, data: bytes, filename: str) -> ExtractionResult:
        try:
            from pypdf import PdfReader
        except ImportError as exc:  # pragma: no cover
            raise ExtractionError("PDF support is not installed") from exc
        try:
            reader = PdfReader(io.BytesIO(data))
            pages: list[ExtractedPage] = []
            parts: list[str] = []
            for i, page in enumerate(reader.pages, start=1):
                page_text = page.extract_text() or ""
                page_text = normalize_text(page_text)
                pages.append(ExtractedPage(i, page_text))
                parts.append(page_text)
            title = None
            if reader.metadata and reader.metadata.title:
                title = str(reader.metadata.title)
            return ExtractionResult(pages=pages, full_text="\n\n".join(parts), title=title, metadata={"pages": len(pages)})
        except ExtractionError:
            raise
        except Exception as exc:
            raise ExtractionError(f"Could not extract text from PDF: {exc}") from exc


class DocxExtractor(DocumentExtractor):
    file_type = "docx"

    def extract(self, data: bytes, filename: str) -> ExtractionResult:
        try:
            import docx
        except ImportError as exc:  # pragma: no cover
            raise ExtractionError("DOCX support is not installed") from exc
        try:
            doc = docx.Document(io.BytesIO(data))
            paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
            text = normalize_text("\n\n".join(paragraphs))
            title = paragraphs[0] if paragraphs else None
            return ExtractionResult(pages=[ExtractedPage(None, text)], full_text=text, title=title)
        except Exception as exc:
            raise ExtractionError(f"Could not extract text from DOCX: {exc}") from exc


_EXTRACTORS: dict[str, type[DocumentExtractor]] = {
    "txt": TextExtractor,
    "md": MarkdownExtractor,
    "pdf": PDFExtractor,
    "docx": DocxExtractor,
}


def get_extractor(file_type: str) -> DocumentExtractor:
    cls = _EXTRACTORS.get(file_type)
    if cls is None:
        raise ExtractionError(f"Unsupported file type: {file_type}")
    return cls()


def register_extractor(file_type: str, extractor_cls: type[DocumentExtractor]) -> None:
    _EXTRACTORS[file_type] = extractor_cls
