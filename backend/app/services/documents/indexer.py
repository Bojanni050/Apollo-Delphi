from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.logging import get_logger
from app.models import Document, DocumentChunk
from app.services.chunking.chunker import Chunk, Chunker
from app.services.documents.service import document_service
from app.services.embeddings.service import EmbeddingService
from app.services.extraction.base import ExtractionResult

log = get_logger(__name__)


class IndexingError(Exception):
    pass


@dataclass
class ReconcileStats:
    added: int = 0
    reused: int = 0  #: kept with their existing embedding
    reembedded: int = 0  #: kept, but to be embedded again (other model or missing vector)
    removed: int = 0


class IndexingService:
    """Indexing in two steps, so a document is usable long before the slow part is done.

    1. ``parse_document``: extraction → chunking → reconcile with the stored chunks. Quick (a fraction of a second). The
       document is then ``parsed``: it can be read, its fragments exist and it is searchable by words.
    2. ``embed_document``: embed the fragments that have no vector of the active model, a batch at a time, storing each batch
       as it comes. Slow (seconds per fragment on a CPU). The document is ``indexed`` when none is missing; until then
       semantic search already uses the fragments that are done.

    ``index_document`` does both, one after the other.
    """

    def __init__(self, embedding_service: EmbeddingService | None = None, chunker: Chunker | None = None):
        self.embedding_service = embedding_service or EmbeddingService()
        self.chunker = chunker or Chunker()
        self.last_stats = ReconcileStats()

    def _has_current_embedding(self, row: DocumentChunk) -> bool:
        return (
            row.embedding is not None
            and row.embedding_model == self.embedding_service.model
            and row.embedding_dim == len(row.embedding)
        )

    def _reconcile_chunks(self, db: Session, document_id: int, chunks: list[Chunk]) -> ReconcileStats:
        """Bring the stored chunks in line with ``chunks``; nothing is embedded here.

        A chunk is identified by its text. A stored row whose text is still present is kept (same id, so claims and
        evidence pointing at it survive) and gets its position, page, section and line range refreshed; its embedding
        stays, and ``embed_document`` replaces it when it was made with another model. Rows whose text is gone are
        deleted; text without a row is inserted (without an embedding). Duplicate texts are matched one to one.
        """
        existing: dict[str, list[DocumentChunk]] = {}
        rows = (
            db.query(DocumentChunk)
            .filter(DocumentChunk.document_id == document_id)
            .order_by(DocumentChunk.chunk_index, DocumentChunk.id)
            .all()
        )
        for row in rows:
            existing.setdefault(row.content, []).append(row)

        stats = ReconcileStats()
        for chunk in chunks:
            candidates = existing.get(chunk.content)
            row = candidates.pop(0) if candidates else None
            if row is None:
                row = DocumentChunk(document_id=document_id, content=chunk.content)
                db.add(row)
                stats.added += 1
            elif self._has_current_embedding(row):
                stats.reused += 1
            else:
                stats.reembedded += 1
            row.chunk_index, row.page_number, row.section = chunk.chunk_index, chunk.page_number, chunk.section
            row.line_start, row.line_end = chunk.line_start, chunk.line_end

        for leftover in existing.values():
            for row in leftover:
                db.delete(row)
                stats.removed += 1
        db.flush()
        self.last_stats = stats
        log.info("Reconciled document %s: %s", document_id, stats)
        return stats

    def _missing_embeddings(self, db: Session, document_id: int) -> list[DocumentChunk]:
        rows = (
            db.query(DocumentChunk)
            .filter(DocumentChunk.document_id == document_id)
            .order_by(DocumentChunk.chunk_index, DocumentChunk.id)
            .all()
        )
        return [r for r in rows if not self._has_current_embedding(r)]

    async def parse_document(self, db: Session, document_id: int) -> Document:
        """Extract, chunk and store the fragments (no embedding): the document becomes ``parsed``, or ``indexed`` when
        every fragment already has a vector of the active model."""
        doc = db.get(Document, document_id)
        if doc is None:
            raise IndexingError(f"Document {document_id} not found")
        if doc.indexing_status == "processing":
            raise IndexingError("Document is already being indexed")

        doc.indexing_status = "processing"
        doc.error_message = None
        db.commit()

        try:
            extraction = document_service.extract(doc)
            chunks = self.chunker.chunk(extraction)
            if not chunks:
                raise IndexingError("No text content could be extracted from the document")
            self._reconcile_chunks(db, doc.id, chunks)
            missing = bool(self._missing_embeddings(db, doc.id))
        except Exception as exc:
            log.exception("Parsing failed for document %s", document_id)
            db.rollback()
            doc = db.get(Document, document_id)
            doc.indexing_status = "failed"
            doc.error_message = str(exc)[:2000]
            db.commit()
            db.refresh(doc)
            return doc

        doc.indexing_status = "parsed" if missing else "indexed"
        if not missing:
            doc.indexed_at = dt.datetime.now(dt.timezone.utc)
        doc.error_message = None
        if extraction.title and not doc.title:
            doc.title = extraction.title[:512]
        db.commit()
        db.refresh(doc)
        return doc

    async def embed_document(self, db: Session, document_id: int) -> Document:
        """Embed the fragments without a vector of the active model, a batch at a time, storing each batch as it comes.

        A failure (the model is not reachable) keeps what is done, leaves the document ``parsed`` (so it stays readable and
        searchable by words) and records the reason in ``error_message``; asking again continues with what is missing.
        """
        doc = db.get(Document, document_id)
        if doc is None:
            raise IndexingError(f"Document {document_id} not found")
        if doc.indexing_status not in ("parsed", "indexed"):
            raise IndexingError(f"Document is {doc.indexing_status}: parse it first")

        missing = self._missing_embeddings(db, doc.id)
        batch = max(1, get_settings().embedding_batch_size)
        try:
            for start in range(0, len(missing), batch):
                part = missing[start : start + batch]
                vectors = await self.embedding_service.embed_documents([row.content for row in part])
                for row, vector in zip(part, vectors):
                    emb = list(vector)
                    row.embedding, row.embedding_model, row.embedding_dim = emb, self.embedding_service.model, len(emb)
                db.commit()
        except Exception as exc:
            log.exception("Embedding failed for document %s", document_id)
            db.rollback()
            doc = db.get(Document, document_id)
            doc.indexing_status = "parsed"
            doc.error_message = f"Embedden mislukt: {str(exc)[:1900]}"
            db.commit()
            db.refresh(doc)
            return doc

        doc = db.get(Document, document_id)
        doc.indexing_status = "indexed"
        doc.indexed_at = dt.datetime.now(dt.timezone.utc)
        doc.error_message = None
        db.commit()
        db.refresh(doc)
        return doc

    async def index_document(self, db: Session, document_id: int) -> Document:
        doc = await self.parse_document(db, document_id)
        if doc.indexing_status == "failed":
            return doc
        return await self.embed_document(db, document_id)
