from __future__ import annotations

import datetime as dt
import json

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.models.document import READY_STATUSES

#: The value that stands for "the documents without a group" (the same one the search API takes).
NO_GROUP = "__none__"
from app.models import (
    AnalysisRun,
    Claim,
    ClaimEvidence,
    Document,
    DocumentChunk,
    Evidence,
    Issue,
    IssueClaim,
    IssueEvidence,
)
from app.services.search.service import evidence_lines
from app.services.analysis.progress import analysis_progress
from app.services.analysis.claim_extraction import ExtractedClaim, get_claim_extractor, normalize_value
from app.services.issues.detection import (
    detect_entity_contradictions,
    DetectedContradiction,
    DetectedOpenQuestion,
    detect_contradictions,
    detect_open_questions,
)

log = get_logger(__name__)


class AnalysisError(Exception):
    pass


class AnalysisService:
    """Runs the full analysis pipeline over the indexed collection.

    Stage order: claim extraction → evidence persistence → open-question
    detection → contradiction detection → issue persistence. Every stage's
    output is persisted as inspectable relational data before the next runs.
    """

    def run_analysis(self, db: Session, workspace_id: int | None = None, groups: list[str] | None = None) -> AnalysisRun:
        """Analyse the documents of a werkmap (without one: the documents that belong to no werkmap).

        ``groups`` limits the run to the documents of those groups (virtual folders; ``"__none__"`` = the ones without a group):
        claims, open questions and contradictions are then found among those documents only, so one subject (or two) can be
        looked at at a time, and a run is much smaller. Omitted or empty = every document.
        """
        run, doc_ids = self.create_run(db, workspace_id, groups)
        return self.execute_run(db, run.id, doc_ids)

    def create_run(self, db: Session, workspace_id: int | None = None, groups: list[str] | None = None) -> tuple[AnalysisRun, list[int]]:
        """Choose the documents and record the run as running; ``execute_run`` does the work (the page starts it in the background)."""
        query = db.query(Document).filter(Document.indexing_status.in_(READY_STATUSES), Document.workspace_id == workspace_id)
        groups = [g for g in dict.fromkeys(groups or []) if g]
        if groups:
            named = [g for g in groups if g != NO_GROUP]
            wanted = Document.group_name.in_(named) if named else None
            if NO_GROUP in groups:
                wanted = Document.group_name.is_(None) if wanted is None else (wanted | Document.group_name.is_(None))
            query = query.filter(wanted)
        docs = query.all()
        run = AnalysisRun(status="running", workspace_id=workspace_id, stats=json.dumps({"groups": groups}) if groups else None)
        db.add(run)
        db.commit()
        db.refresh(run)
        analysis_progress.start(run.id, workspace_id)
        return run, [d.id for d in docs]

    def execute_run(self, db: Session, run_id: int, doc_ids: list[int]) -> AnalysisRun:
        run = db.get(AnalysisRun, run_id)
        groups = (json.loads(run.stats).get("groups") if run.stats else None) or []
        docs = db.query(Document).filter(Document.id.in_(doc_ids)).order_by(Document.id).all() if doc_ids else []
        try:
            claims_count, questions_count, contradictions_count = self._analyze(db, run, docs)
            run.status = "completed"
            run.stats = json.dumps(
                {
                    "documents_analyzed": len(docs),
                    "claims": claims_count,
                    "open_questions": questions_count,
                    "contradictions": contradictions_count,
                    **({"groups": groups} if groups else {}),
                }
            )
            run.completed_at = dt.datetime.now(dt.timezone.utc)
            db.commit()
            analysis_progress.event(run.id, "stage", f"Klaar: {claims_count} claims, {questions_count} open vragen, {contradictions_count} tegenstrijdigheden")
            analysis_progress.update(run.id, stage="klaar", current_document=None)
        except Exception as exc:
            db.rollback()
            run = db.get(AnalysisRun, run.id)
            run.status = "failed"
            run.error_message = str(exc)[:2000]
            db.commit()
            db.refresh(run)
            analysis_progress.event(run.id, "stage", f"Mislukt: {str(exc)[:160]}")
            analysis_progress.update(run.id, stage="mislukt", error=str(exc)[:500], current_document=None)
            raise
        db.refresh(run)
        return run

    def _analyze(self, db: Session, run: AnalysisRun, docs: list[Document]) -> tuple[int, int, int]:
        extractor = get_claim_extractor()
        doc_by_id = {d.id: d for d in docs}
        extracted: list[tuple[ExtractedClaim, int, DocumentChunk]] = []
        persisted_open_questions: list[DetectedOpenQuestion] = []
        progress = analysis_progress
        chunks_total = (
            db.query(func.count(DocumentChunk.id)).filter(DocumentChunk.document_id.in_([d.id for d in docs])).scalar() if docs else 0
        )
        progress.update(run.id, stage="lezen", documents_total=len(docs), chunks_total=chunks_total)
        progress.event(run.id, "stage", f"Start: {len(docs)} documenten, {chunks_total} fragmenten")

        for number, doc in enumerate(docs, start=1):
            progress.update(run.id, current_document=doc.filename)
            progress.event(run.id, "document", f"Lezen: {doc.filename} ({number} van {len(docs)})")
            chunks = (
                db.query(DocumentChunk)
                .filter(DocumentChunk.document_id == doc.id)
                .order_by(DocumentChunk.chunk_index)
                .all()
            )
            for chunk in chunks:
                for claim in extractor.extract(chunk.content):
                    extracted.append((claim, doc.id, chunk))
                    progress.add(run.id, claims=1)
                    progress.event(run.id, "claim", f"{doc.filename}: {claim.statement}")
                for q in detect_open_questions(chunk.content):
                    self._persist_open_question(db, run, doc, chunk, q)
                    persisted_open_questions.append(q)
                    progress.add(run.id, open_questions=1)
                    progress.event(run.id, "question", f"{doc.filename}: {q.question}")
                progress.add(run.id, chunks_done=1)
            progress.add(run.id, documents_done=1)

        progress.update(run.id, stage="opslaan", current_document=None)
        progress.event(run.id, "stage", f"Claims opslaan met hun bewijs ({len(extracted)})")
        persisted: list[tuple[Claim, int]] = []
        for claim, doc_id, chunk in extracted:
            c = self._persist_claim(db, run, claim, doc_by_id[doc_id], chunk)
            persisted.append((c, doc_id))
        progress.update(run.id, stage="vergelijken")
        progress.event(run.id, "stage", "Claims met elkaar vergelijken op tegenstrijdigheden")

        claim_rows = db.query(Claim).filter(Claim.analysis_run_id == run.id).all()
        row_pairs: list[tuple[Claim, int]] = [(c, c.document_id) for c in claim_rows]
        extracteds = [
                (
                    ExtractedClaim(
                        statement=c.statement,
                        subject=c.subject,
                        predicate=c.predicate,
                        value=c.value,
                        unit=c.unit,
                        qualifiers=c.qualifiers,
                        quote=c.claim_metadata_obj.get("quote", c.statement),
                        confidence=c.confidence,
                    ),
                    doc_id,
                )
            for c, doc_id in row_pairs
        ]
        contradictions = _dedupe_contradictions(
            detect_contradictions(extracteds) + detect_entity_contradictions(extracteds)
        )
        claim_by_quote: dict[str, Claim] = {}
        for claim_row in claim_rows:
            quote = claim_row.claim_metadata_obj.get("quote", claim_row.statement)
            claim_by_quote.setdefault(quote, claim_row)
            claim_by_quote.setdefault(claim_row.statement, claim_row)

        real_contradictions: list[DetectedContradiction] = []
        for contra in contradictions:
            ca = claim_by_quote.get(contra.claim_a.quote) or claim_by_quote.get(contra.claim_a.statement)
            cb = claim_by_quote.get(contra.claim_b.quote) or claim_by_quote.get(contra.claim_b.statement)
            if ca is None or cb is None:
                continue
            ca.status, cb.status = "disputed", "disputed"
            self._persist_contradiction(db, run, contra, ca, cb)
            real_contradictions.append(contra)
            progress.add(run.id, contradictions=1)
            progress.event(run.id, "contradiction", f"Tegenstrijdig: {contra.key}: {contra.value_a} tegenover {contra.value_b}")

        db.commit()
        return len(persisted), len(persisted_open_questions), len(real_contradictions)

    def _persist_claim(self, db: Session, run: AnalysisRun, ex: ExtractedClaim, doc: Document, chunk: DocumentChunk) -> Claim:
        quote_lines = evidence_lines(doc, chunk, ex.quote)
        evidence = Evidence(
            document_id=doc.id,
            chunk_id=chunk.id,
            evidence_type="explicit",
            page_number=chunk.page_number,
            section=chunk.section,
            line_start=quote_lines[0],
            line_end=quote_lines[1],
            original_text=ex.quote,
            normalized_text=ex.quote,
            extraction_metadata=json.dumps({"extractor": "claim_extraction", "chunk_id": chunk.id}),
        )
        db.add(evidence)
        db.flush()
        claim = Claim(
            analysis_run_id=run.id,
            document_id=doc.id,
            statement=ex.statement,
            subject=ex.subject,
            predicate=ex.predicate,
            value=ex.value,
            value_normalized=normalize_value(ex.value) if ex.value else None,
            unit=ex.unit,
            qualifiers=ex.qualifiers,
            claim_metadata=json.dumps({"extractor_confidence": ex.confidence, "quote": ex.quote}),
            confidence=ex.confidence,
            status="unresolved",
        )
        db.add(claim)
        db.flush()
        db.add(ClaimEvidence(claim_id=claim.id, evidence_id=evidence.id, relation="supports"))
        db.flush()
        return claim

    def _persist_open_question(self, db: Session, run: AnalysisRun, doc: Document, chunk: DocumentChunk, q: DetectedOpenQuestion) -> Issue:
        quote_lines = evidence_lines(doc, chunk, q.source_quote)
        evidence = Evidence(
            document_id=doc.id,
            chunk_id=chunk.id,
            evidence_type="explicit",
            page_number=chunk.page_number,
            section=chunk.section,
            line_start=quote_lines[0],
            line_end=quote_lines[1],
            original_text=q.source_quote,
            extraction_metadata=json.dumps({"detector": "open_questions", "marker": q.marker}),
        )
        db.add(evidence)
        db.flush()
        issue = Issue(
            analysis_run_id=run.id,
            issue_type="open_question",
            title=f"Open question in {doc.filename}",
            description=f"The source explicitly leaves a question unanswered: {q.question}",
            question=q.question,
            status="open",
            severity="warning",
            issue_metadata=json.dumps({"marker": q.marker}),
        )
        db.add(issue)
        db.flush()
        db.add(IssueEvidence(issue_id=issue.id, evidence_id=evidence.id, relevance=1.0))
        db.flush()
        return issue

    def _persist_contradiction(
        self, db: Session, run: AnalysisRun, d: DetectedContradiction, ca: Claim, cb: Claim
    ) -> Issue:
        issue = Issue(
            analysis_run_id=run.id,
            issue_type="contradiction",
            title=f"Conflicting values for '{d.key}': {d.value_a} vs {d.value_b}",
            description=(
                f"Two indexed documents state different values for '{d.key}' "
                f"({d.value_a} vs {d.value_b})."
            ),
            question=f"Which value for '{d.key}' is correct?",
            status="open",
            severity="error",
            issue_metadata=json.dumps({"key": d.key, "value_a": d.value_a, "value_b": d.value_b}),
        )
        db.add(issue)
        db.flush()
        for role, claim in (("claim_a", ca), ("claim_b", cb)):
            db.add(IssueClaim(issue_id=issue.id, claim_id=claim.id, role=role))
            for link in claim.evidence_links:
                db.add(IssueEvidence(issue_id=issue.id, evidence_id=link.evidence_id, relevance=0.9))
        db.flush()
        return issue


analysis_service = AnalysisService()


def recover_interrupted_analyses() -> int:
    """Analyses that were running when the app stopped cannot continue: mark them failed (they would stay "running" for ever)."""
    from app.db.session import SessionLocal

    db = SessionLocal()
    try:
        count = (
            db.query(AnalysisRun)
            .filter(AnalysisRun.status == "running")
            .update({"status": "failed", "error_message": "Onderbroken doordat de app stopte"})
        )
        db.commit()
        return count
    finally:
        db.close()


def _dedupe_contradictions(found: list) -> list:
    """Drop contradictions that cover the same claim pair (quote pair)."""
    seen: set[tuple[str, str]] = set()
    out = []
    for contra in found:
        pair = tuple(sorted([contra.claim_a.quote, contra.claim_b.quote]))
        if pair in seen:
            continue
        seen.add(pair)
        out.append(contra)
    return out
