from __future__ import annotations

import datetime as dt
import json
import re

from pydantic import BaseModel, Field, ValidationError
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.llm import LLMError, LLMProvider, get_llm_provider
from app.core.logging import get_logger
from app.models import Claim, Evidence, Investigation, Issue, IssueEvidence, Resolution
from app.services.search.service import SearchService

log = get_logger(__name__)


class ProposedResolution(BaseModel):
    """Structured proposal for resolving an issue."""

    status: str = Field(description="'resolved' or 'unresolved'")
    conclusion: str | None = Field(default=None, description="The conclusion, only if resolved")
    reasoning: str | None = Field(default=None)
    explanation_type: str | None = Field(
        default=None,
        description=(
            "One of: supersedes, error_in_document, different_context, changed_over_time, "
            "valid_under_different_conditions, insufficient_evidence"
        ),
    )
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    supporting_evidence_indices: list[int] = Field(default_factory=list)
    unresolved_uncertainty: str | None = Field(default=None)


class InvestigationEngine:
    """Detection and resolution are separate stages.

    Investigation: retrieve relevant evidence across the whole collection
    (semantic search + issue-linked evidence), compare claims, reason about
    the evidence, and produce a structured resolution proposal.
    """

    def __init__(self, llm: LLMProvider | None = None, search: SearchService | None = None):
        self.llm = llm or get_llm_provider()
        self.search = search or SearchService()

    async def investigate(self, db: Session, issue: Issue) -> Investigation:
        investigation = Investigation(issue_id=issue.id, model_provider=self.llm.name, model_name=get_settings().llm_model)
        db.add(investigation)
        db.commit()
        db.refresh(investigation)

        evidence_rows = await self._gather_evidence(db, issue)
        findings = await self._reason(db, issue, evidence_rows)

        investigation.evidence_summary = json.dumps(
            [
                {
                    "document_id": e.document_id,
                    "page_number": e.page_number,
                    "excerpt": e.original_text[:200],
                }
                for e in evidence_rows
            ]
        )
        investigation.findings = json.dumps(findings)
        investigation.completed_at = dt.datetime.now(dt.timezone.utc)
        db.commit()
        db.refresh(investigation)
        return investigation

    @staticmethod
    def _workspace_document_ids(db: Session, issue: Issue) -> list[int]:
        """Ids of the documents in the werkmap this issue's analysis ran on (unassigned documents for legacy runs)."""
        from app.models import AnalysisRun, Document

        run = db.get(AnalysisRun, issue.analysis_run_id)
        workspace_id = run.workspace_id if run is not None else None
        rows = db.query(Document.id).filter(Document.workspace_id == workspace_id).all()
        return [r[0] for r in rows]

    async def _gather_evidence(self, db: Session, issue: Issue) -> list[Evidence]:
        """Evidence linked to the issue plus semantically retrieved evidence from the collection."""
        linked = (
            db.query(Evidence)
            .join(IssueEvidence, IssueEvidence.evidence_id == Evidence.id)
            .filter(IssueEvidence.issue_id == issue.id)
            .all()
        )
        results: list[Evidence] = list(linked)
        seen_ids = {e.id for e in linked}

        query_text = issue.question or issue.title
        scope = self._workspace_document_ids(db, issue)
        hits = []
        if scope:  # an empty scope must not fall back to searching every werkmap
            try:
                hits = await self.search.search(db, query_text, top_k=5, document_ids=scope)
            except Exception as exc:
                log.warning("Semantic evidence retrieval failed for issue %s: %s", issue.id, exc)

        from app.models import DocumentChunk

        for hit in hits:
            chunk = db.get(DocumentChunk, hit.chunk_id)
            if chunk is None:
                continue
            for e in (
                db.query(Evidence).filter(Evidence.chunk_id == chunk.id).all()
            ):
                if e.id not in seen_ids:
                    seen_ids.add(e.id)
                    results.append(e)
            if chunk.id not in {c.chunk_id for c in results}:
                ev = Evidence(
                    document_id=hit.document_id,
                    chunk_id=chunk.id,
                    evidence_type="explicit",
                    page_number=hit.page_number,
                    section=hit.section,
                    line_start=hit.line_start,
                    line_end=hit.line_end,
                    original_text=chunk.content[:2000],
                    extraction_metadata=json.dumps({"retrieved_for_issue": issue.id, "similarity": hit.similarity}),
                )
                db.add(ev)
                db.flush()
                db.add(IssueEvidence(issue_id=issue.id, evidence_id=ev.id, relevance=hit.similarity))
                results.append(ev)
        db.commit()
        return results

    async def _reason(self, db: Session, issue: Issue, evidence: list[Evidence]) -> dict:
        claims = self._issue_claims(db, issue)
        context = self._build_context(db, issue, claims, evidence)

        if get_settings().llm_provider == "mock":
            proposal = self._deterministic_reason(db, issue, claims, evidence)
        else:
            system = (
                "You are an evidence-driven investigation engine. Stage: issue_investigation. "
                "Compare the conflicting claims, weigh the evidence (document dates, explicit "
                "supersession statements, contexts), and propose a resolution. "
                "If the evidence is insufficient, return status='unresolved'. "
                "Never invent evidence. Prefer explicit uncertainty over fabricated certainty."
            )
            user = (
                f"Issue: {issue.title}\nType: {issue.issue_type}\nQuestion: {issue.question or ''}\n\n"
                f"Context:\n{context}\n\n"
                "Respond as JSON with keys status, conclusion, reasoning, explanation_type, "
                "confidence, supporting_evidence_indices, unresolved_uncertainty. "
                "supporting_evidence_indices refers to the numbered evidence entries above."
            )
            try:
                proposal = await self.llm.complete_json(system, user, ProposedResolution)
            except (LLMError, ValidationError) as exc:
                log.warning("Investigation LLM failed for issue %s: %s", issue.id, exc)
                proposal = ProposedResolution(
                    status="unresolved",
                    unresolved_uncertainty="The investigation model returned an unusable answer, so this issue remains unresolved.",
                )

        return {
            "status": proposal.status,
            "conclusion": proposal.conclusion,
            "reasoning": proposal.reasoning,
            "explanation_type": proposal.explanation_type,
            "confidence": proposal.confidence,
            "supporting_evidence_indices": proposal.supporting_evidence_indices,
            "unresolved_uncertainty": proposal.unresolved_uncertainty,
        }

    def _find_supersession_statement(self, db: Session, claims: list[Claim]):
        """Scan the chunks of the involved documents for explicit supersession statements."""
        from app.models import Document, DocumentChunk

        _SUPERSEDES_RE = re.compile(r"supersedes|supersede|superseded|replaces\b|revised budget|amends", re.IGNORECASE)
        doc_ids = sorted({c.document_id for c in claims})
        if len(doc_ids) < 2:
            return None
        for doc_id in doc_ids:
            chunks = (
                db.query(DocumentChunk)
                .filter(DocumentChunk.document_id == doc_id)
                .order_by(DocumentChunk.chunk_index)
                .all()
            )
            for chunk in chunks:
                m = _SUPERSEDES_RE.search(chunk.content)
                if m:
                    winner = next((c for c in claims if c.document_id == doc_id), None)
                    if winner is not None:
                        doc = db.get(Document, doc_id)
                        return winner, doc, chunk.content
        return None

    def _issue_claims(self, db: Session, issue: Issue) -> list[Claim]:
        from app.models import IssueClaim

        return (
            db.query(Claim)
            .join(IssueClaim, IssueClaim.claim_id == Claim.id)
            .filter(IssueClaim.issue_id == issue.id)
            .all()
        )

    def _build_context(self, db: Session, issue: Issue, claims: list[Claim], evidence: list[Evidence]) -> str:
        from app.models import Document

        lines: list[str] = []
        for i, ev in enumerate(evidence):
            doc = db.get(Document, ev.document_id)
            doc_date = doc.document_date.isoformat() if doc and doc.document_date else "unknown"
            lines.append(
                f"[Evidence {i}] document={doc.filename if doc else ev.document_id} "
                f"date={doc_date} page={ev.page_number} type={ev.evidence_type}: {ev.original_text[:300]}"
            )
        for c in claims:
            doc = db.get(Document, c.document_id)
            lines.append(
                f"[Claim] document={doc.filename if doc else c.document_id}: {c.statement} "
                f"(value={c.value} {c.unit or ''})"
            )
        return "\n".join(lines)

    def _deterministic_reason(self, db: Session, issue: Issue, claims: list[Claim], evidence: list[Evidence]) -> ProposedResolution:
        """Heuristic reasoning used with the mock LLM provider.

        Implements real evidence-based rules: (1) explicit supersession statements
        in evidence, (2) latest document date wins among conflicting claims when
        dates are known, (3) otherwise explicitly unresolved.
        """
        from app.models import Document

        if issue.issue_type == "open_question":
            return ProposedResolution(
                status="unresolved",
                reasoning="The source explicitly marks this question as unanswered; no evidence resolves it.",
                explanation_type="insufficient_evidence",
                confidence=0.1,
                unresolved_uncertainty="No evidence in the collection answers this question.",
            )

        if len(claims) < 2:
            return ProposedResolution(
                status="unresolved",
                reasoning="Fewer than two conflicting claims are available to reason about.",
                explanation_type="insufficient_evidence",
                confidence=0.0,
                unresolved_uncertainty="Insufficient evidence.",
            )

        for ev in evidence:
            text = ev.original_text.lower()
            if re.search(r"supersedes|replaces|supersede|superseded|revised budget|amends", text):
                doc = db.get(Document, ev.document_id)
                winner = next((c for c in claims if c.document_id == ev.document_id), claims[0])
                return ProposedResolution(
                    status="resolved",
                    conclusion=f"'{winner.subject}' is {winner.value} {winner.unit or ''}".strip() + f" (per {doc.filename})."
                    if doc
                    else f"'{winner.subject}' is {winner.value} {winner.unit or ''}".strip(),
                    reasoning=(
                        f"Evidence in {doc.filename if doc else 'a later document'} explicitly supersedes "
                        "the earlier statement, so the conflicting claim is outdated."
                    ),
                    explanation_type="supersedes",
                    confidence=0.9,
                    supporting_evidence_indices=[i for i, e in enumerate(evidence) if e.id == ev.id],
                )

        supersedes_winner = self._find_supersession_statement(db, claims)
        if supersedes_winner is not None:
            winner, winner_doc, marker_quote = supersedes_winner
            return ProposedResolution(
                status="resolved",
                conclusion=(
                    f"'{winner.subject}' is {winner.value} {winner.unit or ''}".strip()
                    + f" (per {winner_doc.filename})."
                ),
                reasoning=(
                    f"{winner_doc.filename} explicitly states it supersedes the earlier document "
                    f"(\"{marker_quote[:200]}\"), so the conflicting claim in the earlier source is outdated."
                ),
                explanation_type="supersedes",
                confidence=0.85,
                supporting_evidence_indices=[i for i, e in enumerate(evidence) if e.document_id == winner.document_id],
            )

        dated = []
        for c in claims:
            doc = db.get(Document, c.document_id)
            if doc and doc.document_date:
                dated.append((doc.document_date, c, doc))
        if len({d for d, _c, _doc in dated}) >= 2:
            dated.sort(key=lambda t: t[0])
            latest_date, winner, winner_doc = dated[-1]
            loser_doc = db.get(Document, [c for c in claims if c.id != winner.id][0].document_id)
            return ProposedResolution(
                status="resolved",
                conclusion=(
                    f"'{winner.subject}' is {winner.value} {winner.unit or ''}".strip()
                    + f" (current as of {winner_doc.filename}, {latest_date.isoformat()})."
                ),
                reasoning=(
                    f"{winner_doc.filename} is dated ({latest_date.isoformat()}) after the conflicting source"
                    f" ({loser_doc.filename if loser_doc else 'earlier document'}), and later documents "
                    "are taken to reflect the current state."
                ),
                explanation_type="changed_over_time",
                confidence=0.7,
                supporting_evidence_indices=[i for i, e in enumerate(evidence) if e.document_id == winner.document_id],
                unresolved_uncertainty=(
                    "No explicit supersession statement was found; resolution relies on document dates."
                ),
            )

        return ProposedResolution(
            status="unresolved",
            reasoning="The available evidence does not indicate which conflicting claim is correct.",
            explanation_type="insufficient_evidence",
            confidence=0.0,
            unresolved_uncertainty="No dates or supersession statements distinguish the conflicting sources.",
        )


class ResolutionEngine:
    """Persists explicit Resolution objects and applies outcomes to claims/issues."""

    def persist(self, db: Session, issue: Issue, proposal: dict) -> Resolution:
        status = proposal.get("status", "unresolved")
        if status not in ("resolved", "unresolved"):
            status = "unresolved"
        resolution = Resolution(
            issue_id=issue.id,
            status=status,
            conclusion=proposal.get("conclusion"),
            reasoning=proposal.get("reasoning"),
            explanation_type=proposal.get("explanation_type"),
            confidence=float(proposal.get("confidence") or 0.0),
            source_refs=json.dumps(proposal.get("supporting_evidence_indices", [])),
            unresolved_uncertainty=proposal.get("unresolved_uncertainty"),
            model_provider=get_llm_provider().name,
            model_name=get_settings().llm_model,
            resolved_by="apollo",
        )
        db.add(resolution)
        db.flush()

        issue.status = status
        if status == "resolved":
            for link in issue.claim_links:
                winning = self._winning_claim(db, issue, resolution)
                if winning is not None:
                    link.claim.status = "confirmed" if link.claim.id == winning else "superseded"
        db.commit()
        db.refresh(resolution)
        return resolution

    def _winning_claim(self, db: Session, issue: Issue, resolution: Resolution) -> int | None:
        if not resolution.conclusion:
            return None
        best: tuple[float, int] | None = None
        for link in issue.claim_links:
            claim = link.claim
            if claim.value and claim.value in resolution.conclusion:
                if best is None or claim.confidence > best[0]:
                    best = (claim.confidence, claim.id)
        return best[1] if best else None

    def apply_human_decision(self, db: Session, resolution: Resolution, decision: str, note: str | None, user: str = "user") -> Resolution:
        from app.models import HumanDecision

        if decision not in ("accept", "reject", "unresolved"):
            raise ValueError("decision must be accept, reject, or unresolved")
        db.add(HumanDecision(resolution_id=resolution.id, decision=decision, note=note, decided_by=user))
        issue = resolution.issue
        if decision == "accept":
            issue.status = "resolved"
            resolution.status = "resolved"
        elif decision in ("reject", "unresolved"):
            issue.status = "unresolved"
            resolution.status = "unresolved"
            resolution.unresolved_uncertainty = note or resolution.unresolved_uncertainty
        db.commit()
        db.refresh(resolution)
        return resolution
