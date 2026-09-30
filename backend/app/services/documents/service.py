from __future__ import annotations

import hashlib
import re
import secrets
from pathlib import Path
import datetime as dt

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.logging import get_logger
from app.db.session import SessionLocal
from app.models import Document, Workspace
from app.services.extraction.extractors import get_extractor
from app.services import workspace_repo
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
    def create_document(self, db: Session, filename: str, data: bytes, workspace_id: int | None = None) -> Document:
        ext = validate_upload(filename, data)
        stored, content_hash = store_file(data, ext)
        doc = Document(
            filename=filename[:512],
            stored_filename=stored,
            file_type=ext.lstrip("."),
            file_size=len(data),
            content_hash=content_hash,
            indexing_status="pending",
            workspace_id=workspace_id,
        )
        ws = db.get(Workspace, workspace_id) if workspace_id is not None else None
        if ws is not None:
            doc.repo_path = self._mirror_into_repo(db, ws, filename, data)
        db.add(doc)
        db.commit()
        db.refresh(doc)
        return doc

    def _mirror_into_repo(self, db: Session, ws: Workspace, filename: str, data: bytes) -> str | None:
        """Keep the original in the werkmap's repository. Failing here must not lose the upload."""
        try:
            if ws.working_dir is None:  # werkmap created before werkmappen were repositories
                ws.working_dir = str(workspace_repo.init_repo(workspace_repo.default_working_dir(ws.id, ws.name)))
            return workspace_repo.store_in_inbox(Path(ws.working_dir), filename, data)
        except (OSError, workspace_repo.GitError) as exc:
            log.warning("Could not store %s in werkmap %s: %s", filename, ws.id, exc)
            return None

    def get_document(self, db: Session, document_id: int) -> Document | None:
        return db.get(Document, document_id)

    def list_documents(self, db: Session, workspace_id: int | None = None) -> list[Document]:
        q = db.query(Document)
        if workspace_id is not None:
            q = q.filter(Document.workspace_id == workspace_id)
        return q.order_by(Document.created_at.desc()).all()

    def delete_document(self, db: Session, document_id: int) -> bool:
        doc = db.get(Document, document_id)
        if doc is None:
            return False
        if doc.source_type == "github":
            db.delete(doc)
            db.commit()
            return True
        path = get_settings().ensure_upload_dir() / doc.stored_filename
        try:
            path.unlink(missing_ok=True)
        except OSError:
            log.warning("Could not delete stored file for document %s", document_id)
        db.delete(doc)
        db.commit()
        return True

    def read_file(self, doc: Document) -> bytes:
        if doc.source_type == "github":
            from app.services.github.service import github_ingest_service

            content = github_ingest_service.get_document_content(doc)
            if content is None:
                raise DocumentValidationError(f"Kon GitHub-inhoud voor {doc.repo_path} niet ophalen")
            return content
        path = get_settings().ensure_upload_dir() / doc.stored_filename
        return path.read_bytes()

    def extract(self, doc: Document) -> ExtractionResult:
        data = self.read_file(doc)
        extractor = get_extractor(doc.file_type)
        return extractor.extract(data, doc.filename)


document_service = DocumentService()
