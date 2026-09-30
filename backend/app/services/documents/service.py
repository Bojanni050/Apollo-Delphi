from __future__ import annotations

import hashlib
import re
import secrets
import datetime as dt

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.session import SessionLocal
from app.models import Document
from app.services.extraction.extractors import get_extractor
from app.services.extraction.base import ExtractionError, ExtractionResult, normalize_text

log = get_logger(__name__)


class DocumentValidationError(Exception):
    pass


_SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9._-]+")


def _safe_extension(filename: str) -> str:
    name = filename.strip().lower()
    if "/" in name or "\\" in name or ".." in name:
        raise DocumentValidationError("Invalid filename")
    dot = name.rfind(".")
    if dot == -1:
        raise DocumentValidationError("File has no extension")
    ext = name[dot:]
    if ext not in get_settings().allowed_extensions:
        raise DocumentValidationError(f"Unsupported file type '{ext}'. Allowed: {get_settings().allowed_extensions}")
    return ext


def validate_upload(filename: str, data: bytes) -> str:
    ext = _safe_extension(filename)
    if not data:
        raise DocumentValidationError("Uploaded file is empty")
    limit = get_settings().max_upload_size_bytes
    if len(data) > limit:
        raise DocumentValidationError(f"File exceeds the {get_settings().max_upload_size_mb} MB upload limit")
    return ext


def store_file(data: bytes, ext: str) -> tuple[str, str]:
    """Persist the upload under a server-generated name. Returns (stored_filename, content_hash)."""
    content_hash = hashlib.sha256(data).hexdigest()
    stored = f"{secrets.token_hex(8)}-{content_hash[:12]}{_SAFE_NAME_RE.sub('_', ext)}"
    path = get_settings().ensure_upload_dir() / stored
    path.write_bytes(data)
    return stored, content_hash


class DocumentService:
    def create_document(self, db: Session, filename: str, data: bytes) -> Document:
        ext = validate_upload(filename, data)
        stored, content_hash = store_file(data, ext)
        doc = Document(
            filename=filename[:512],
            stored_filename=stored,
            file_type=ext.lstrip("."),
            file_size=len(data),
            content_hash=content_hash,
            indexing_status="pending",
        )
        db.add(doc)
        db.commit()
        db.refresh(doc)
        return doc

    def get_document(self, db: Session, document_id: int) -> Document | None:
        return db.get(Document, document_id)

    def list_documents(self, db: Session) -> list[Document]:
        return db.query(Document).order_by(Document.created_at.desc()).all()

    def delete_document(self, db: Session, document_id: int) -> bool:
        doc = db.get(Document, document_id)
        if doc is None:
            return False
        path = get_settings().ensure_upload_dir() / doc.stored_filename
        try:
            path.unlink(missing_ok=True)
        except OSError:
            log.warning("Could not delete stored file for document %s", document_id)
        db.delete(doc)
        db.commit()
        return True

    def read_file(self, doc: Document) -> bytes:
        path = get_settings().ensure_upload_dir() / doc.stored_filename
        return path.read_bytes()

    def extract(self, doc: Document) -> ExtractionResult:
        data = self.read_file(doc)
        extractor = get_extractor(doc.file_type)
        return extractor.extract(data, doc.filename)


document_service = DocumentService()
