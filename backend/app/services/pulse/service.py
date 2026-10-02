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
from pathlib import Path

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.llm import LLMError, LLMProvider, get_llm_provider, model_for
from app.core.logging import get_logger
from app.services import workspace_repo
from app.services.workspace_repo import TYPE_FOLDERS
from app.models.document import READY_STATUSES
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
    folder: str = ""
    group: str = ""


class _PulseBatch(BaseModel):
    documents: list[_PulseDoc] = Field(default_factory=list)


def _system_prompt() -> str:
    return (
        "Stage: pulse. You analyse a collection of documents. For each document you receive, "
        "produce a concise summary (one sentence), 1-5 thematic tags (single words or short "
        "hyphenated phrases, lowercase), and connections to OTHER documents from the provided id "
        "list only. A connection states the relation (relates-to, supports, contradicts, extends) "
        "and one short sentence why, naming documents by filename and never by id. Only connect documents when the content genuinely supports "
        "it; an empty connection list is a valid answer. "
        "Also sort each document. folder: the TYPE of document, one of the given type folders (what kind of text it is: a draft, a "
        "report, a chapter of a book, notes, a specification, reference material); only when none fits at all, propose ONE new short "
        "folder name in English (a single capitalised word). group: the SUBJECT the document belongs to within this collection, a short "
        "lowercase label (for example 'architecture' or 'foundation'); reuse one of the existing groups when it fits, so that related "
        "documents share a group, and create a new one only when none does. Respond with JSON only, shaped as "
        '{"documents": [{"id": "...", "summary": "...", "tags": ["..."], '
        '"connections": [{"id": "...", "relation": "relates-to", "why": "..."}], "folder": "Reports", "group": "...", "confidence": 0.0}]}.'
    )


def _user_prompt(batch: list[tuple[Document, str]], all_docs: list[Document], groups: list[str] | None = None) -> str:
    return "\n".join(
        [
            "Type folders: " + json.dumps(list(TYPE_FOLDERS)),
            "Existing groups: " + json.dumps(sorted(groups or []), ensure_ascii=False),
            "",
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


_GROUP_JUNK_RE = re.compile(r"[^\w -]+", re.UNICODE)


def _clean_group(name: str | None) -> str | None:
    """A group (virtual folder): lowercase words, no odd characters, at most 40 long."""
    cleaned = re.sub(r"\s+", " ", _GROUP_JUNK_RE.sub(" ", str(name or "")).strip(" _-")).strip().lower()[:40].strip(" -_")
    return cleaned or None


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
        "folder": workspace_repo.clean_folder_name(entry.folder),
        "group": _clean_group(entry.group),
    }


def _top_terms(text: str, n: int = 5) -> list[str]:
    counts = Counter(w.lower() for w in _WORD_RE.findall(text) if w.lower() not in _STOPWORDS)
    return [w for w, _ in counts.most_common(n)]


_MOCK_FOLDER_HINTS = (
    ("Drafts", ("draft", "concept", "versie")),
    ("Reports", ("report", "rapport", "verslag")),
    ("Chapters", ("chapter", "hoofdstuk")),
    ("Specs", ("spec", "architect", "ontwerp", "design")),
    ("Notes", ("note", "notitie", "memo")),
    ("Reference", ("readme", "reference", "referentie", "handleiding", "guide")),
)


def _mock_folder(name: str, text: str) -> str:
    haystack = (name + " " + text[:300]).lower()
    for folder, hints in _MOCK_FOLDER_HINTS:
        if any(h in haystack for h in hints):
            return folder
    return "Other"


def _mock_group(name: str) -> str | None:
    """The folder a file came from ("corpus/Gaia/architectuur/a.md" -> "architectuur"), when it came from one."""
    parts = [p for p in name.replace("\\", "/").split("/") if p]
    return _clean_group(parts[-2]) if len(parts) >= 2 else None


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
            "folder": _mock_folder(names[doc_id], texts[doc_id]),
            "group": _mock_group(names[doc_id]),
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
            .filter(Document.workspace_id == workspace.id, Document.indexing_status.in_(READY_STATUSES))
            .order_by(Document.id)
            .all()
        )
        texts = {d.id: _read_text(d) for d in docs}
        todo = [d for d in docs if texts[d.id].strip() and (force or _last_hash(db, d.id) != d.content_hash)]
        errors: list[str] = []
        created = 0
        # groups that exist already (accepted before, or proposed in this run): offered to the model so documents share them
        groups = {
            g
            for (g,) in db.query(Document.group_name)
            .filter(Document.workspace_id == workspace.id, Document.group_name.isnot(None))
            .distinct()
        }

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
                            _system_prompt(), _user_prompt([(d, texts[d.id]) for d in batch], docs, sorted(groups)), _PulseBatch
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
                            if results[doc_id]["group"]:
                                groups.add(results[doc_id]["group"])
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
                        folder=r.get("folder"),
                        group_name=r.get("group"),
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

    @staticmethod
    def _apply(db: Session, item: PulseItem, decision: str) -> None:
        if decision not in ("accepted", "dismissed"):
            raise PulseError(f"Unknown decision: {decision}")
        item.decision = decision
        if decision == "accepted":
            doc = db.get(Document, item.document_id)
            meta = json.loads(doc.doc_metadata or "{}")
            meta["tags"] = json.loads(item.tags)
            meta["connections"] = json.loads(item.connections)
            doc.doc_metadata = json.dumps(meta, ensure_ascii=False)
            if item.group_name:
                doc.group_name = item.group_name

    def decide(self, db: Session, item: PulseItem, decision: str) -> PulseItem:
        """Record a human decision. Accepting merges tags and connections into the document's metadata."""
        self._apply(db, item, decision)
        db.commit()
        db.refresh(item)
        moved = self._move_files(db, item.workspace_id, [item], decision)
        self._log_to_repo(db, item.workspace_id, [item], decision, moved)
        return item

    @staticmethod
    def _move_files(db: Session, workspace_id: int, items: list[PulseItem], decision: str) -> dict[int, str]:
        """After accepting: move the documents into their type folders in the werkmap's repository (one commit).

        Returns {document id: new path}. Only after the decision itself is saved, so a git problem leaves the decision in place
        and the file where it was (with a warning in the log). Documents without a copy in the repository are left alone.
        """
        if decision != "accepted":
            return {}
        try:
            ws = db.get(Workspace, workspace_id)
            if ws is None or ws.working_dir is None:
                return {}
            docs = {d.id: d for d in db.query(Document).filter(Document.id.in_([i.document_id for i in items]))}
            wanted = [(docs[i.document_id], i.folder) for i in items if i.folder and i.document_id in docs and docs[i.document_id].inbox_path]
            if not wanted:
                return {}
            if len(wanted) == 1:
                message = f"Move {wanted[0][0].inbox_path} to {wanted[0][1]}/"
            else:
                message = f"Move {len(wanted)} documents into type folders\n\n" + "\n".join(f"- {d.inbox_path} -> {f}/" for d, f in wanted[:50])
            done = workspace_repo.move_into_folders(Path(ws.working_dir), [(d.inbox_path, f) for d, f in wanted], message)
            moved: dict[int, str] = {}
            for d, _ in wanted:
                if d.inbox_path in done:
                    moved[d.id] = d.inbox_path = done[d.inbox_path]
            db.commit()
            return moved
        except (OSError, workspace_repo.GitError) as exc:
            db.rollback()
            log.warning("Could not move documents of werkmap %s into their type folders: %s", workspace_id, exc)
            return {}

    @staticmethod
    def _log_to_repo(db: Session, workspace_id: int, items: list[PulseItem], decision: str, moved: dict[int, str] | None = None) -> None:
        """Write the decision(s) into the werkmap's git repository. Failing here must not undo a decision."""
        if not items:
            return
        try:
            ws = db.get(Workspace, workspace_id)
            if ws is None:
                return
            if ws.working_dir is None:  # werkmap created before werkmappen were repositories
                ws.working_dir = str(workspace_repo.init_repo(workspace_repo.default_working_dir(ws.id, ws.name)))
                db.commit()
            now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
            names = {d.id: (d.inbox_path or d.filename) for d in db.query(Document).filter(Document.workspace_id == workspace_id)}
            entries = []
            for item in items:
                connections = [
                    {"document": names.get(c.get("document_id"), f"document {c.get('document_id')}"), "relation": c.get("relation"), "why": c.get("why", "")}
                    for c in json.loads(item.connections)
                ]
                entries.append({
                    "at": now,
                    "kind": "pulse",
                    "decision": decision,
                    "document": names.get(item.document_id, f"document {item.document_id}"),
                    "summary": item.summary,
                    "folder": item.folder,
                    "group": item.group_name,
                    "moved_to": (moved or {}).get(item.document_id),
                    "tags": json.loads(item.tags),
                    "connections": connections,
                })
            verb = "accepted" if decision == "accepted" else "dismissed"
            if len(items) == 1:
                message = f"Pulse: {verb} {entries[0]['document']}"
            else:
                message = f"Pulse: {verb} {len(items)} suggestions\n\n" + "\n".join(f"- {e['document']}" for e in entries[:50])
            workspace_repo.record_decisions(Path(ws.working_dir), entries, message)
        except (OSError, workspace_repo.GitError) as exc:
            log.warning("Could not record the Pulse decision in werkmap %s: %s", workspace_id, exc)

    def decide_all(self, db: Session, workspace_id: int, decision: str) -> int:
        """Decide every suggestion of the werkmap that still awaits one, in one go (all or nothing). Returns how many."""
        if decision not in ("accepted", "dismissed"):
            raise PulseError(f"Unknown decision: {decision}")
        items = (
            db.query(PulseItem)
            .filter(PulseItem.workspace_id == workspace_id, PulseItem.decision == "pending")
            .order_by(PulseItem.id)
            .all()
        )
        try:
            for item in items:
                self._apply(db, item, decision)
            db.commit()
        except Exception:
            db.rollback()
            raise
        moved = self._move_files(db, workspace_id, items, decision)
        self._log_to_repo(db, workspace_id, items, decision, moved)
        return len(items)
