from __future__ import annotations

import datetime as dt

from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.models import Document, DocumentChunk
from app.services.chunking.chunker import Chunker
from app.services.documents.service import document_service
from app.services.embeddings.service import EmbeddingService
from app.services.extraction.base import ExtractionResult

log = get_logger(__name__)


class IndexingError(Exception):
    pass


class IndexingService:
    """Pipeline: extraction → normalization → chunking → embedding → vector storage."""

    def __init__(self, embedding_service: EmbeddingService | None = None, chunker: Chunker | None = None):
        self.embedding_service = embedding_service or EmbeddingService()
        self.chunker = chunker or Chunker()

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
            embeddings = await self.embedding_service.embed_documents([c.content for c in chunks])
            db.query(DocumentChunk).filter(DocumentChunk.document_id == doc.id).delete()
            db.flush()
            for chunk, emb in zip(chunks, embeddings):
                db.add(
                    DocumentChunk(
                        document_id=doc.id,
                        chunk_index=chunk.chunk_index,
                        page_number=chunk.page_number,
                        section=chunk.section,
                        content=chunk.content,
                        embedding=list(emb),
                    )
                )
            db.flush()
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
