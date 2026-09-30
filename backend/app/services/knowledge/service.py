from __future__ import annotations

import datetime as dt
import json

from sqlalchemy.orm import Session

from app.core.logging import get_logger
from app.models import AnalysisRun, Claim, Issue, KnowledgeItem, Resolution

log = get_logger(__name__)

ITEM_TYPES = ("fact", "derived_conclusion", "assumption", "decision", "unresolved_question", "resolved_contradiction", "remaining_contradiction")


class KnowledgeService:
    """Constructs the coherent knowledge state after analysis/resolution.

    Distinguishes facts (undisputed claims), derived conclusions, assumptions,
    decisions, unresolved questions, resolved contradictions, and remaining
    contradictions. Every item keeps traceability to its sources.
    """

    def build_knowledge_state(self, db: Session, analysis_run_id: int) -> list[KnowledgeItem]:
        run = db.get(AnalysisRun, analysis_run_id)
        if run is None:
            raise ValueError(f"Analysis run {analysis_run_id} not found")
        db.query(KnowledgeItem).filter(KnowledgeItem.analysis_run_id == analysis_run_id).delete()
        db.flush()

        claims = db.query(Claim).filter(Claim.analysis_run_id == analysis_run_id).all()
        issues = db.query(Issue).filter(Issue.analysis_run_id == analysis_run_id).all()
        resolutions = {
            r.issue_id: r for r in db.query(Resolution).join(Issue, Issue.id == Resolution.issue_id).filter(Issue.analysis_run_id == analysis_run_id).all()
        }

        disputed_claim_ids = {link.claim_id for i in issues for link in i.claim_links}
        items: list[KnowledgeItem] = []

        for claim in claims:
            if claim.id in disputed_claim_ids:
                continue
            items.append(
                KnowledgeItem(
                    analysis_run_id=analysis_run_id,
                    item_type="fact",
                    statement=claim.statement,
                    confidence=claim.confidence,
                    provenance="extracted claim",
                    source_refs=json.dumps([f"claim:{claim.id}"] + [f"evidence:{e.id}" for e in claim.evidence_items]),
                )
            )

        for issue in issues:
            resolution = resolutions.get(issue.id)
            if issue.issue_type == "open_question":
                items.append(
                    KnowledgeItem(
                        analysis_run_id=analysis_run_id,
                        item_type="unresolved_question" if not (resolution and resolution.status == "resolved") else "resolved_contradiction",
                        statement=issue.question or issue.title,
                        explanation=(resolution.conclusion if resolution and resolution.status == "resolved" else issue.description),
                        confidence=resolution.confidence if resolution else 0.0,
                        provenance="open question issue" + (f", resolved by {resolution.explanation_type}" if resolution else ""),
                        source_refs=json.dumps([f"issue:{issue.id}"]),
                    )
                )
                continue
            if resolution and resolution.status == "resolved":
                items.append(
                    KnowledgeItem(
                        analysis_run_id=analysis_run_id,
                        item_type="resolved_contradiction",
                        statement=resolution.conclusion or issue.title,
                        explanation=resolution.reasoning,
                        confidence=resolution.confidence,
                        provenance=f"contradiction resolved ({resolution.explanation_type})",
                        source_refs=json.dumps([f"issue:{issue.id}", f"resolution:{resolution.id}"]),
                    )
                )
            else:
                items.append(
                    KnowledgeItem(
                        analysis_run_id=analysis_run_id,
                        item_type="remaining_contradiction",
                        statement=issue.title,
                        explanation=issue.description,
                        confidence=0.0,
                        provenance="unresolved contradiction",
                        source_refs=json.dumps([f"issue:{issue.id}"]),
                    )
                )

        db.add_all(items)
        db.commit()
        return items

    def get_knowledge_state(
        self, db: Session, analysis_run_id: int | None = None, workspace_id: int | None = None
    ) -> list[KnowledgeItem]:
        """Knowledge of a run, or of the latest completed analysis of a werkmap (none = unassigned)."""
        q = db.query(KnowledgeItem)
        if analysis_run_id:
            q = q.filter(KnowledgeItem.analysis_run_id == analysis_run_id)
        else:
            latest = (
                db.query(AnalysisRun)
                .filter(AnalysisRun.status == "completed", AnalysisRun.workspace_id == workspace_id)
                .order_by(AnalysisRun.id.desc())
                .first()
            )
            if latest is None:
                return []
            q = q.filter(KnowledgeItem.analysis_run_id == latest.id)
        return q.order_by(KnowledgeItem.item_type, KnowledgeItem.id).all()
