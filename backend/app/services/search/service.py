from __future__ import annotations

import json
import math
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.services.embeddings.service import EmbeddingService


class SearchError(Exception):
    pass


@dataclass
class SearchHit:
    chunk_id: int
    document_id: int
    document_filename: str
    excerpt: str
    page_number: int | None
    section: str | None
    similarity: float


class SearchService:
    def __init__(self, embedding_service: EmbeddingService | None = None):
        self.embedding_service = embedding_service or EmbeddingService()

    async def search(self, db: Session, query: str, top_k: int | None = None, document_ids: list[int] | None = None) -> list[SearchHit]:
        query = query.strip()
        if not query:
            return []
        k = top_k or get_settings().search_top_k
        qvec = await self.embedding_service.embed_query(query)

        if db.get_bind().dialect.name == "postgresql":
            return self._search_pgvector(db, qvec, k, document_ids, self.embedding_service.model)
        return self._search_fallback(db, qvec, k, document_ids, self.embedding_service.model)

    def _search_pgvector(self, db: Session, qvec: list[float], k: int, document_ids: list[int] | None, model: str) -> list[SearchHit]:
        vec_literal = "[" + ",".join(f"{float(v):.6f}" for v in qvec) + "]"
        sql = text(
            """
            SELECT c.id, c.document_id, d.filename, c.content,
                   COALESCE(c.page_number, -1) AS page_number,
                   COALESCE(c.section, '') AS section,
                   1 - (c.embedding <=> :vec) AS similarity
            FROM document_chunks c
            JOIN documents d ON d.id = c.document_id
            WHERE c.embedding IS NOT NULL
              AND c.embedding_model = :model
              AND c.embedding_dim = :dim
              AND d.indexing_status = 'indexed'
              AND (:has_docs = FALSE OR c.document_id = ANY(:doc_ids))
            ORDER BY c.embedding <=> :vec
            LIMIT :k
            """
        )
        rows = db.execute(
            sql,
            {"vec": vec_literal, "model": model, "dim": len(qvec), "k": k, "has_docs": bool(document_ids), "doc_ids": document_ids or []},
        ).fetchall()
        return [
            SearchHit(
                chunk_id=row.id,
                document_id=row.document_id,
                document_filename=row.filename,
                excerpt=row.content,
                page_number=row.page_number if row.page_number != -1 else None,
                section=row.section or None,
                similarity=float(row.similarity),
            )
            for row in rows
        ]

    def _search_fallback(self, db: Session, qvec: list[float], k: int, document_ids: list[int] | None, model: str) -> list[SearchHit]:
        from app.models import Document, DocumentChunk

        rows = (
            db.query(DocumentChunk, Document)
            .join(Document, Document.id == DocumentChunk.document_id)
            .filter(
                DocumentChunk.embedding.isnot(None),
                DocumentChunk.embedding_model == model,
                DocumentChunk.embedding_dim == len(qvec),
                Document.indexing_status == "indexed",
            )
            .all()
        )
        scored: list[tuple[float, DocumentChunk, Document]] = []
        for chunk, doc in rows:
            if document_ids and chunk.document_id not in document_ids:
                continue
            emb = chunk.embedding
            if isinstance(emb, str):
                emb = json.loads(emb)
            sim = _cosine(qvec, emb)
            if sim is not None:
                scored.append((max(0.0, min(1.0, sim)), chunk, doc))
        scored.sort(key=lambda t: t[0], reverse=True)
        return [
            SearchHit(
                chunk_id=chunk.id,
                document_id=doc.id,
                document_filename=doc.filename,
                excerpt=chunk.content,
                page_number=chunk.page_number,
                section=chunk.section,
                similarity=sim,
            )
            for sim, chunk, doc in scored[:k]
        ]


def _cosine(a: list[float], b: list[float]) -> float | None:
    if not a or not b or len(a) != len(b):
        return None
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return None
    return dot / (na * nb)
