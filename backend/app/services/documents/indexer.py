from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from sqlalchemy.orm import Session

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
    reembedded: int = 0  #: kept, but embedded again (other model or missing vector)
    removed: int = 0


class IndexingService:
    """Pipeline: extraction → normalization → chunking → reconcile with stored chunks → embedding → storage."""

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

    async def _reconcile_chunks(self, db: Session, document_id: int, chunks: list[Chunk]) -> ReconcileStats:
        """Bring the stored chunks in line with ``chunks`` and embed only what is new.

        A chunk is identified by its text. A stored row whose text is still present is kept (same id, so
        claims and evidence pointing at it survive) and gets its position, page, section and line range refreshed. Its
        embedding is reused when it was made with the active model, and recomputed otherwise. Rows whose
        text is gone are deleted; text without a row is inserted. Duplicate texts are matched one to one.
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

        matched: list[DocumentChunk | None] = []
        for chunk in chunks:
            candidates = existing.get(chunk.content)
            matched.append(candidates.pop(0) if candidates else None)

        to_embed = [c.content for c, row in zip(chunks, matched) if row is None or not self._has_current_embedding(row)]
        vectors = iter(await self.embedding_service.embed_documents(to_embed) if to_embed else [])

        stats = ReconcileStats()
        for chunk, row in zip(chunks, matched):
            if row is None:
                row = DocumentChunk(document_id=document_id, content=chunk.content)
                db.add(row)
                stats.added += 1
            elif self._has_current_embedding(row):
                stats.reused += 1
            else:
                stats.reembedded += 1
            if not self._has_current_embedding(row):
                emb = list(next(vectors))
                row.embedding, row.embedding_model, row.embedding_dim = emb, self.embedding_service.model, len(emb)
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

    async def index_document(self, db: Session, document_id: int) -> Document:
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
            await self._reconcile_chunks(db, doc.id, chunks)
        except Exception as exc:
            log.exception("Indexing failed for document %s", document_id)
            db.rollback()
            doc = db.get(Document, document_id)
            doc.indexing_status = "failed"
            doc.error_message = str(exc)[:2000]
            db.commit()
            db.refresh(doc)
            return doc

        doc.indexing_status = "indexed"
        doc.indexed_at = dt.datetime.now(dt.timezone.utc)
        doc.error_message = None
        if extraction.title and not doc.title:
            doc.title = extraction.title[:512]
        db.commit()
        db.refresh(doc)
        return doc
