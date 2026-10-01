"""Hybrid search: semantic (vectors) + keyword (full-text), fused with Reciprocal Rank Fusion.

Why both: embeddings find paraphrases ("money set aside for repairing the dock" -> a harbour
budget) but are unreliable for exact tokens such as amounts, names and identifiers
("250000", "Maria Chen", "ADR-0042"), which are exactly what claims and contradictions are made of.
A keyword leg finds those exactly. Each leg returns a ranked list; RRF merges them without having
to compare their incompatible scores:

    score(chunk) = 1 / (k + rank_semantic) + 1 / (k + rank_keyword)        (k = 60)

A chunk found by only one leg still scores; a chunk found by both ranks above either alone.

Keyword leg: PostgreSQL full-text (`to_tsvector('simple', content)`, a GIN expression index) and
`ts_rank_cd`; SQLite (dev/tests) has no full-text type, so a small in-memory BM25 is used instead.
The 'simple' configuration is language-neutral (no stemming, no stopword list of its own), which
suits mixed Dutch/English documents and exact tokens; common words are dropped here instead.

Keyword search does not depend on embeddings, so chunks embedded with another (or an older) model
are still found by it; only the semantic leg is limited to the active model.
"""
from __future__ import annotations

import json
import math
import re
from collections import Counter
from dataclasses import dataclass, field

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.embeddings import EmbeddingError
from app.core.logging import get_logger
from app.models.document import READY_STATUSES
from app.services.embeddings.service import EmbeddingService

log = get_logger(__name__)

MODES = ("hybrid", "semantic", "keyword")
MAX_QUERY_TERMS = 32
MAX_CANDIDATES = 200

_TOKEN_RE = re.compile(r"\w[\w.,'-]*\w|\w", re.UNICODE)
_STOPWORDS = frozenset(
    """a an and are as at be by for from has have how i in is it of on or that the this to was were what when
    where which who why will with do does did can could should would not no been into than then them their
    de het een en van voor met niet zijn wordt worden door naar maar ook als bij dat die dit deze heeft hebben
    er te op aan om uit zo dan wat wie waar wanneer hoe waarom kan kunnen moet mag""".split()
)


def has_citable_lines(doc: Document) -> bool:
    """Line numbers only mean something for an uploaded text file, where they are the file's own lines.

    For pdf and docx they number the extracted text, and a GitHub digest is a stitched-together text of many
    files; neither can be found back in anything the reader can open.
    """
    return doc.source_type == "upload" and doc.file_type in ("txt", "md")


def evidence_lines(doc: Document, chunk: DocumentChunk, quote: str | None = None) -> tuple[int | None, int | None]:
    """Line range for evidence taken from ``chunk``: the quote's own lines when it is found in the chunk,
    otherwise the whole chunk's. (None, None) when lines are not citable or were never recorded."""
    if chunk.line_start is None or not has_citable_lines(doc):
        return None, None
    start, end = chunk.line_start, chunk.line_end
    body = chunk.content.lstrip()  # line_start is the chunk's first line with text
    quote = (quote or "").strip()
    at = body.find(quote) if quote else -1
    if at >= 0:
        start = chunk.line_start + body.count("\n", 0, at)
        end = start + quote.count("\n")
    return start, end


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
    #: Cosine similarity with the query when the chunk was embedded by the active model, else 0.
    similarity: float
    #: Reciprocal-rank-fusion score (hybrid) or the single leg's reciprocal rank.
    score: float = 0.0
    #: Which leg(s) found it: "semantic", "keyword" or "both".
    match: str = "semantic"
    #: Inclusive line range in the uploaded text file, when known: only txt/md uploads (see has_citable_lines),
    #: and not for chunks indexed before line ranges existed.
    line_start: int | None = None
    line_end: int | None = None


@dataclass
class _Candidate:
    chunk_id: int
    similarity: float = 0.0


@dataclass
class _Fused:
    chunk_id: int
    score: float
    semantic_rank: int | None = None
    keyword_rank: int | None = None
    sources: list[str] = field(default_factory=list)


def query_terms(query: str) -> list[str]:
    """Searchable terms: lower-cased, de-duplicated, without common words; digits and identifiers are kept."""
    seen: list[str] = []
    for raw in _TOKEN_RE.findall(query.lower()):
        token = raw.strip(".,'-")
        if len(token) < 2 and not token.isdigit():
            continue
        if token in _STOPWORDS or token in seen:
            continue
        seen.append(token)
    return seen[:MAX_QUERY_TERMS]


def rrf_fuse(semantic: list[int], keyword: list[int], k: int = 60) -> list[_Fused]:
    """Merge two ranked id lists (best first) with Reciprocal Rank Fusion; best fused score first."""
    fused: dict[int, _Fused] = {}
    for leg, ids in (("semantic", semantic), ("keyword", keyword)):
        for rank, chunk_id in enumerate(ids, start=1):
            entry = fused.setdefault(chunk_id, _Fused(chunk_id=chunk_id, score=0.0))
            entry.score += 1.0 / (k + rank)
            entry.sources.append(leg)
            if leg == "semantic":
                entry.semantic_rank = rank
            else:
                entry.keyword_rank = rank
    # ties: found by both legs first, then the better individual rank, then id (deterministic)
    return sorted(
        fused.values(),
        key=lambda f: (-f.score, -len(f.sources), min(r for r in (f.semantic_rank, f.keyword_rank) if r), f.chunk_id),
    )


def bm25_rank(docs: dict[int, str], terms: list[str], k1: float = 1.5, b: float = 0.75) -> list[int]:
    """Rank chunk ids by BM25 for ``terms`` (best first); chunks matching no term are left out."""
    if not terms or not docs:
        return []
    tokenised = {cid: [t.strip(".,'-") for t in _TOKEN_RE.findall(content.lower())] for cid, content in docs.items()}
    n = len(tokenised)
    avg_len = (sum(len(t) for t in tokenised.values()) / n) or 1.0
    doc_freq = {term: sum(1 for toks in tokenised.values() if term in toks) for term in terms}
    scores: dict[int, float] = {}
    for cid, toks in tokenised.items():
        counts = Counter(toks)
        score = 0.0
        for term in terms:
            tf = counts.get(term, 0)
            if not tf:
                continue
            idf = math.log(1 + (n - doc_freq[term] + 0.5) / (doc_freq[term] + 0.5))
            score += idf * tf * (k1 + 1) / (tf + k1 * (1 - b + b * len(toks) / avg_len))
        if score > 0:
            scores[cid] = score
    return [cid for cid, _ in sorted(scores.items(), key=lambda kv: (-kv[1], kv[0]))]


class SearchService:
    def __init__(self, embedding_service: EmbeddingService | None = None):
        self.embedding_service = embedding_service or EmbeddingService()
        #: The mode that actually ran (hybrid degrades to keyword when the embedding endpoint fails).
        self.mode_used: str = "hybrid"

    async def search(
        self,
        db: Session,
        query: str,
        top_k: int | None = None,
        document_ids: list[int] | None = None,
        mode: str = "hybrid",
    ) -> list[SearchHit]:
        if mode not in MODES:
            raise SearchError(f"Unknown search mode {mode!r}; use one of {', '.join(MODES)}")
        query = query.strip()
        self.mode_used = mode
        if not query:
            return []
        settings = get_settings()
        k = top_k or settings.search_top_k
        candidates = min(MAX_CANDIDATES, max(k * settings.search_candidate_multiplier, k))
        pg = db.get_bind().dialect.name == "postgresql"

        qvec: list[float] | None = None
        semantic: list[_Candidate] = []
        if mode in ("hybrid", "semantic"):
            try:
                qvec = await self.embedding_service.embed_query(query)
                model = self.embedding_service.model
                semantic = (
                    self._semantic_pg(db, qvec, candidates, document_ids, model)
                    if pg
                    else self._semantic_fallback(db, qvec, candidates, document_ids, model)
                )
            except EmbeddingError as exc:
                if mode == "semantic":
                    raise
                log.warning("Semantic leg unavailable, searching by keywords only: %s", exc)
                self.mode_used = "keyword"

        keyword: list[int] = []
        if self.mode_used in ("hybrid", "keyword"):
            terms = query_terms(query)
            keyword = (
                self._keyword_pg(db, terms, candidates, document_ids)
                if pg
                else self._keyword_fallback(db, terms, candidates, document_ids)
            )

        fused = rrf_fuse([c.chunk_id for c in semantic], keyword, settings.search_rrf_k)[:k]
        return self._hits(db, fused, {c.chunk_id: c.similarity for c in semantic}, qvec)

    # -- semantic leg ---------------------------------------------------------------------------

    def _semantic_pg(self, db: Session, qvec: list[float], n: int, document_ids: list[int] | None, model: str) -> list[_Candidate]:
        vec_literal = "[" + ",".join(f"{float(v):.6f}" for v in qvec) + "]"
        rows = db.execute(
            text(
                """
                SELECT c.id, 1 - (c.embedding <=> :vec) AS similarity
                FROM document_chunks c
                JOIN documents d ON d.id = c.document_id
                WHERE c.embedding IS NOT NULL
                  AND c.embedding_model = :model
                  AND c.embedding_dim = :dim
                  AND d.indexing_status IN ('parsed', 'indexed')
                  AND (:has_docs = FALSE OR c.document_id = ANY(:doc_ids))
                ORDER BY c.embedding <=> :vec
                LIMIT :n
                """
            ),
            {"vec": vec_literal, "model": model, "dim": len(qvec), "n": n, "has_docs": bool(document_ids), "doc_ids": document_ids or []},
        ).fetchall()
        return [_Candidate(r.id, float(r.similarity)) for r in rows]

    def _semantic_fallback(self, db: Session, qvec: list[float], n: int, document_ids: list[int] | None, model: str) -> list[_Candidate]:
        from app.models import Document, DocumentChunk

        rows = (
            db.query(DocumentChunk.id, DocumentChunk.document_id, DocumentChunk.embedding)
            .join(Document, Document.id == DocumentChunk.document_id)
            .filter(
                DocumentChunk.embedding.isnot(None),
                DocumentChunk.embedding_model == model,
                DocumentChunk.embedding_dim == len(qvec),
                Document.indexing_status.in_(READY_STATUSES),
            )
            .all()
        )
        scored: list[_Candidate] = []
        for chunk_id, doc_id, emb in rows:
            if document_ids and doc_id not in document_ids:
                continue
            if isinstance(emb, str):
                emb = json.loads(emb)
            sim = _cosine(qvec, emb)
            if sim is not None:
                scored.append(_Candidate(chunk_id, max(0.0, min(1.0, sim))))
        scored.sort(key=lambda c: (-c.similarity, c.chunk_id))
        return scored[:n]

    # -- keyword leg ----------------------------------------------------------------------------

    def _keyword_pg(self, db: Session, terms: list[str], n: int, document_ids: list[int] | None) -> list[int]:
        if not terms:
            return []
        # One plainto_tsquery per term (PostgreSQL's own parser tokenises "250,000" or "ADR-0042" correctly),
        # OR-ed together: `||` is OR for tsquery. Terms travel as bound parameters, never as SQL text.
        query = " || ".join(f"plainto_tsquery('simple', :t{i})" for i in range(len(terms)))
        params: dict[str, object] = {f"t{i}": term for i, term in enumerate(terms)}
        params.update({"n": n, "has_docs": bool(document_ids), "doc_ids": document_ids or []})
        rows = db.execute(
            text(
                f"""
                SELECT c.id
                FROM document_chunks c
                JOIN documents d ON d.id = c.document_id
                WHERE d.indexing_status IN ('parsed', 'indexed')
                  AND (:has_docs = FALSE OR c.document_id = ANY(:doc_ids))
                  AND to_tsvector('simple', c.content) @@ ({query})
                ORDER BY ts_rank_cd(to_tsvector('simple', c.content), ({query})) DESC, c.id
                LIMIT :n
                """
            ),
            params,
        ).fetchall()
        return [r.id for r in rows]

    def _keyword_fallback(self, db: Session, terms: list[str], n: int, document_ids: list[int] | None) -> list[int]:
        from app.models import Document, DocumentChunk

        if not terms:
            return []
        rows = (
            db.query(DocumentChunk.id, DocumentChunk.document_id, DocumentChunk.content)
            .join(Document, Document.id == DocumentChunk.document_id)
            .filter(Document.indexing_status.in_(READY_STATUSES))
            .all()
        )
        docs = {cid: content for cid, doc_id, content in rows if not document_ids or doc_id in document_ids}
        return bm25_rank(docs, terms)[:n]

    # -- result assembly ------------------------------------------------------------------------

    def _hits(self, db: Session, fused: list[_Fused], similarity: dict[int, float], qvec: list[float] | None) -> list[SearchHit]:
        from app.models import Document, DocumentChunk

        if not fused:
            return []
        rows = {
            chunk.id: (chunk, doc)
            for chunk, doc in db.query(DocumentChunk, Document)
            .join(Document, Document.id == DocumentChunk.document_id)
            .filter(DocumentChunk.id.in_([f.chunk_id for f in fused]))
            .all()
        }
        hits: list[SearchHit] = []
        for f in fused:
            if f.chunk_id not in rows:
                continue
            chunk, doc = rows[f.chunk_id]
            sim = similarity.get(f.chunk_id)
            if sim is None:  # keyword-only hit: still report similarity if the chunk was embedded by the active model
                sim = self._similarity_to_query(chunk, qvec)
            hits.append(
                SearchHit(
                    chunk_id=chunk.id,
                    document_id=doc.id,
                    document_filename=doc.filename,
                    excerpt=chunk.content,
                    page_number=chunk.page_number,
                    section=chunk.section,
                    line_start=chunk.line_start if has_citable_lines(doc) else None,
                    line_end=chunk.line_end if has_citable_lines(doc) else None,
                    similarity=sim,
                    score=f.score,
                    match="both" if len(f.sources) == 2 else f.sources[0],
                )
            )
        return hits

    def _similarity_to_query(self, chunk, qvec: list[float] | None) -> float:
        if qvec is None or chunk.embedding is None or chunk.embedding_dim != len(qvec):
            return 0.0
        if chunk.embedding_model != self.embedding_service.model:
            return 0.0
        emb = chunk.embedding
        if isinstance(emb, str):
            emb = json.loads(emb)
        sim = _cosine(qvec, list(emb))
        return max(0.0, min(1.0, sim)) if sim is not None else 0.0


def _cosine(a: list[float], b: list[float]) -> float | None:
    if not a or not b or len(a) != len(b):
        return None
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return None
    return dot / (na * nb)
