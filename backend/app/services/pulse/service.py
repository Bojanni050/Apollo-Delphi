"""Delphi Pulse: themes and connections across a werkmap's documents.

A run reads each document of a werkmap and asks the *background* model (the cheap
bulk tier) for a one-sentence summary, 1-5 thematic tags and connections to OTHER
documents in the same werkmap, each with a relation and a short reason. The
mock provider gets a deterministic keyword-based implementation so the whole
loop works offline and tests are reproducible.

Rules, taken over from Apollo:

* Pulse only *suggests*. Nothing changes until a person accepts an item; accepting
  copies the tags/connections into the document's metadata. Nothing is deleted.
* Hallucinated ids, self-connections and unknown relations are dropped at the
  boundary, so stored data stays predictable.
* Incremental by content hash: a document is only re-examined when its content
  changed since its last suggestion (``force`` overrides).
"""
from __future__ import annotations

import datetime as dt
import json
import re
from collections import Counter

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.llm import LLMError, LLMProvider, get_llm_provider, model_for
from app.core.logging import get_logger
from app.models import Document, Workspace
from app.models.pulse import PulseItem, PulseRun
from app.services.documents.service import document_service
from app.services.extraction.base import ExtractionError

log = get_logger(__name__)

RELATIONS = frozenset({"relates-to", "supports", "contradicts", "extends"})
MAX_DOCS_PER_REQUEST = 8
MAX_DIGEST_CHARS = 4000

_STOPWORDS = frozenset(
    """that this with from have will been were which their there about would could should into than then them
    also only more most such these those other each over under between after before during while where when what
    de het een van voor met niet zijn wordt worden door naar maar ook als bij dat die dit deze hebben heeft""".split()
)
_WORD_RE = re.compile(r"[a-zA-ZÀ-ɏ][a-zA-ZÀ-ɏ-]{3,}")


class PulseError(RuntimeError):
    pass


class _PulseConnection(BaseModel):
    id: str
    relation: str = "relates-to"
    why: str = ""


class _PulseDoc(BaseModel):
    id: str
    summary: str = ""
    tags: list[str] = Field(default_factory=list)
    connections: list[_PulseConnection] = Field(default_factory=list)
    confidence: float = 0.0


class _PulseBatch(BaseModel):
    documents: list[_PulseDoc] = Field(default_factory=list)


def _system_prompt() -> str:
    return (
        "Stage: pulse. You analyse a collection of documents. For each document you receive, "
        "produce a concise summary (one sentence), 1-5 thematic tags (single words or short "
        "hyphenated phrases, lowercase), and connections to OTHER documents from the provided id "
        "list only. A connection states the relation (relates-to, supports, contradicts, extends) "
        "and one short sentence why, naming documents by filename and never by id. Only connect documents when the content genuinely supports "
        "it; an empty connection list is a valid answer. Respond with JSON only, shaped as "
        '{"documents": [{"id": "...", "summary": "...", "tags": ["..."], '
        '"connections": [{"id": "...", "relation": "relates-to", "why": "..."}], "confidence": 0.0}]}.'
    )


def _user_prompt(batch: list[tuple[Document, str]], all_docs: list[Document]) -> str:
    return "\n".join(
        [
            "Documents to analyse:",
            json.dumps(
                [{"id": str(d.id), "filename": d.filename, "digest": text[:MAX_DIGEST_CHARS]} for d, text in batch],
                ensure_ascii=False,
            ),
            "",
            "All documents in this collection (connections must reference these ids):",
            json.dumps([{"id": str(d.id), "filename": d.filename} for d in all_docs], ensure_ascii=False),
        ]
    )


def _clean(entry: _PulseDoc, own_id: int, valid_ids: set[int]) -> dict:
    tags: list[str] = []
    for t in entry.tags:
        t = str(t).strip().lower()
        if t and t not in tags:
            tags.append(t)
    connections, seen = [], set()
    for c in entry.connections:
        try:
            target = int(c.id)
        except (TypeError, ValueError):
            continue
        relation = c.relation.strip().lower()
        if target in valid_ids and target != own_id and relation in RELATIONS and target not in seen:
            seen.add(target)
            connections.append({"document_id": target, "relation": relation, "why": c.why.strip()[:500]})
    return {
        "summary": entry.summary.strip()[:1000],
        "tags": tags[:5],
        "connections": connections,
        "confidence": max(0.0, min(1.0, float(entry.confidence or 0.0))),
    }


def _top_terms(text: str, n: int = 5) -> list[str]:
    counts = Counter(w.lower() for w in _WORD_RE.findall(text) if w.lower() not in _STOPWORDS)
    return [w for w, _ in counts.most_common(n)]


def _mock_analyse(texts: dict[int, str], names: dict[int, str], targets: list[int]) -> dict[int, dict]:
    """Deterministic stand-in for the model: frequent terms become tags, shared terms become connections."""
    terms = {doc_id: _top_terms(text) for doc_id, text in texts.items()}
    out: dict[int, dict] = {}
    for doc_id in targets:
        mine = terms[doc_id]
        first = texts[doc_id].strip().splitlines()[0][:200] if texts[doc_id].strip() else names[doc_id]
        connections = []
        for other, theirs in terms.items():
            shared = [t for t in mine if t in theirs]
            if other != doc_id and len(shared) >= 2:
                connections.append(
                    {"document_id": other, "relation": "relates-to", "why": f"Both discuss {', '.join(shared[:3])}."}
                )
        out[doc_id] = {
            "summary": first,
            "tags": mine[:3],
            "connections": connections,
            "confidence": 0.5,
        }
    return out


def _read_text(doc: Document) -> str:
    try:
        return document_service.extract(doc).full_text
    except (ExtractionError, OSError) as exc:
        log.warning("Pulse could not read document %s: %s", doc.id, exc)
        return ""


def _last_hash(db: Session, document_id: int) -> str | None:
    row = db.query(PulseItem.content_hash).filter(PulseItem.document_id == document_id).order_by(PulseItem.id.desc()).first()
    return row[0] if row else None


class PulseService:
    def __init__(self, llm: LLMProvider | None = None):
        self._llm = llm

    @property
    def llm(self) -> LLMProvider:
        if self._llm is None:
            self._llm = get_llm_provider("background")
        return self._llm

    async def run(self, db: Session, workspace: Workspace, force: bool = False) -> PulseRun:
        run = PulseRun(workspace_id=workspace.id, provider=self.llm.name, model=model_for("background"))
        db.add(run)
        db.commit()
        db.refresh(run)

        docs = (
            db.query(Document)
            .filter(Document.workspace_id == workspace.id, Document.indexing_status == "indexed")
            .order_by(Document.id)
            .all()
        )
        texts = {d.id: _read_text(d) for d in docs}
        todo = [d for d in docs if texts[d.id].strip() and (force or _last_hash(db, d.id) != d.content_hash)]
        errors: list[str] = []
        created = 0

        if todo:
            valid_ids = {d.id for d in docs}
            results: dict[int, dict] = {}
            if self.llm.name == "mock":
                results = _mock_analyse(texts, {d.id: d.filename for d in docs}, [d.id for d in todo])
            else:
                for i in range(0, len(todo), MAX_DOCS_PER_REQUEST):
                    batch = todo[i : i + MAX_DOCS_PER_REQUEST]
                    try:
                        parsed = await self.llm.complete_json(
                            _system_prompt(), _user_prompt([(d, texts[d.id]) for d in batch], docs), _PulseBatch
                        )
                    except LLMError as exc:
                        errors.append(str(exc))
                        continue
                    batch_ids = {d.id for d in batch}
                    for entry in parsed.documents:  # type: ignore[attr-defined]
                        try:
                            doc_id = int(entry.id)
                        except (TypeError, ValueError):
                            continue
                        if doc_id in batch_ids:
                            results[doc_id] = _clean(entry, doc_id, valid_ids)
            by_id = {d.id: d for d in docs}
            for doc_id, r in results.items():
                db.add(
                    PulseItem(
                        run_id=run.id,
                        workspace_id=workspace.id,
                        document_id=doc_id,
                        content_hash=by_id[doc_id].content_hash,
                        summary=r["summary"],
                        tags=json.dumps(r["tags"], ensure_ascii=False),
                        connections=json.dumps(r["connections"], ensure_ascii=False),
                        confidence=r["confidence"],
                    )
                )
                created += 1

        run.status = "failed" if errors and not created else "completed"
        run.error_message = "; ".join(errors)[:2000] or None
        run.stats = json.dumps({"documents": len(docs), "analysed": created, "skipped": len(docs) - len(todo), "errors": len(errors)})
        run.completed_at = dt.datetime.now(dt.timezone.utc)
        db.commit()
        db.refresh(run)
        return run

    def decide(self, db: Session, item: PulseItem, decision: str) -> PulseItem:
        """Record a human decision. Accepting merges tags and connections into the document's metadata."""
        if decision not in ("accepted", "dismissed"):
            raise PulseError(f"Unknown decision: {decision}")
        item.decision = decision
        if decision == "accepted":
            doc = db.get(Document, item.document_id)
            meta = json.loads(doc.doc_metadata or "{}")
            meta["tags"] = json.loads(item.tags)
            meta["connections"] = json.loads(item.connections)
            doc.doc_metadata = json.dumps(meta, ensure_ascii=False)
        db.commit()
        db.refresh(item)
        return item
