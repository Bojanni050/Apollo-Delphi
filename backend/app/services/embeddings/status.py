"""What the vector index currently holds versus the active embedding model, and re-indexing."""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.embeddings import EmbeddingError, get_embedding_provider
from app.core.logging import get_logger
from app.models import Document, DocumentChunk
from app.models.document import READY_STATUSES

log = get_logger(__name__)


@dataclass
class IndexStatus:
    model: str | None
    dimensions: int | None
    provider: str | None
    error: str | None
    chunks_total: int
    chunks_current: int
    documents_indexed: int
    documents_stale: int
    by_model: dict[str, int]


def _stale_document_ids(db: Session, model: str | None, workspace_id: int | None) -> list[int]:
    """Documents with no chunk embedded by the active model (old model, legacy, or missing), and every ``parsed`` one."""
    q = db.query(Document.id).filter(Document.indexing_status.in_(READY_STATUSES))
    if workspace_id is not None:
        q = q.filter(Document.workspace_id == workspace_id)
    ids = [r[0] for r in q.order_by(Document.id).all()]
    if not ids:
        return []
    current = {
        r[0]
        for r in db.query(DocumentChunk.document_id)
        .filter(DocumentChunk.document_id.in_(ids), DocumentChunk.embedding_model == model)
        .distinct()
        .all()
    }
    parsed = {r[0] for r in db.query(Document.id).filter(Document.id.in_(ids), Document.indexing_status == "parsed").all()}
    return [i for i in ids if i not in current or i in parsed]


def index_status(db: Session, workspace_id: int | None = None) -> IndexStatus:
    model = dims = provider_name = error = None
    try:
        provider = get_embedding_provider()
        model, dims, provider_name = provider.model, provider.dimensions, provider.name
    except EmbeddingError as exc:
        error = str(exc)

    chunks = db.query(DocumentChunk).join(Document, Document.id == DocumentChunk.document_id)
    if workspace_id is not None:
        chunks = chunks.filter(Document.workspace_id == workspace_id)
    by_model = {
        (m or "none"): n
        for m, n in chunks.with_entities(DocumentChunk.embedding_model, func.count(DocumentChunk.id))
        .group_by(DocumentChunk.embedding_model)
        .all()
    }
    indexed = db.query(Document).filter(Document.indexing_status == "indexed")
    if workspace_id is not None:
        indexed = indexed.filter(Document.workspace_id == workspace_id)
    return IndexStatus(
        model=model,
        dimensions=dims,
        provider=provider_name,
        error=error,
        chunks_total=sum(by_model.values()),
        chunks_current=by_model.get(model, 0) if model else 0,
        documents_indexed=indexed.count(),
        documents_stale=len(_stale_document_ids(db, model, workspace_id)) if model else 0,
        by_model=by_model,
    )


async def reindex(db: Session, workspace_id: int | None = None, everything: bool = False) -> dict:
    """Re-embed documents with the active model. Only stale ones unless ``everything``."""
    from app.services.documents.indexer import IndexingService

    provider = get_embedding_provider()
    if everything:
        q = db.query(Document.id).filter(Document.indexing_status.in_(("parsed", "indexed", "failed")))
        if workspace_id is not None:
            q = q.filter(Document.workspace_id == workspace_id)
        ids = [r[0] for r in q.order_by(Document.id).all()]
    else:
        ids = _stale_document_ids(db, provider.model, workspace_id)
    service = IndexingService()
    done, failed = 0, []
    for doc_id in ids:
        doc = await service.index_document(db, doc_id)
        if doc.indexing_status == "indexed":
            done += 1
        else:
            failed.append({"document_id": doc_id, "error": doc.error_message})
    return {"model": provider.model, "requested": len(ids), "reindexed": done, "failed": failed}
