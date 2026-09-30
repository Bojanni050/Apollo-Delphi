from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_session
from app.models import Claim, Evidence, Issue, IssueClaim, IssueEvidence, Resolution
from app.schemas.issues import ClaimOut, EvidenceOut, IssueDetail, IssueOut, ResolveRequest, ResolutionOut
from app.services.issues.investigation import InvestigationEngine, ResolutionEngine

router = APIRouter(prefix="/issues", tags=["issues"])


@router.get("", response_model=list[IssueOut])
def list_issues(status: str | None = None, db: Session = Depends(get_session)):
    q = db.query(Issue)
    if status:
        q = q.filter(Issue.status == status)
    return q.order_by(Issue.created_at.desc()).all()


@router.get("/{issue_id}", response_model=IssueDetail)
def get_issue(issue_id: int, db: Session = Depends(get_session)):
    issue = db.get(Issue, issue_id)
    if issue is None:
        raise HTTPException(status_code=404, detail="Issue not found")
    claims = (
        db.query(Claim)
        .join(IssueClaim, IssueClaim.claim_id == Claim.id)
        .filter(IssueClaim.issue_id == issue.id)
        .all()
    )
    evidence = (
        db.query(Evidence)
        .join(IssueEvidence, IssueEvidence.evidence_id == Evidence.id)
        .filter(IssueEvidence.issue_id == issue.id)
        .all()
    )
    resolution = (
        db.query(Resolution).filter(Resolution.issue_id == issue.id).order_by(Resolution.id.desc()).first()
    )
    return IssueDetail(
        id=issue.id,
        analysis_run_id=issue.analysis_run_id,
        issue_type=issue.issue_type,
        title=issue.title,
        description=issue.description,
        question=issue.question,
        status=issue.status,
        severity=issue.severity,
        created_at=issue.created_at,
        claims=[ClaimOut.model_validate(c) for c in claims],
        evidence=[EvidenceOut.model_validate(e) for e in evidence],
        resolution=ResolutionOut.model_validate(resolution) if resolution else None,
    )


@router.post("/{issue_id}/investigate", response_model=IssueDetail)
async def investigate_issue(issue_id: int, db: Session = Depends(get_session)):
    issue = db.get(Issue, issue_id)
    if issue is None:
        raise HTTPException(status_code=404, detail="Issue not found")
    issue.status = "investigating"
    db.commit()
    engine = InvestigationEngine()
    investigation = await engine.investigate(db, issue)
    proposal = investigation.findings
    import json

    resolution = ResolutionEngine().persist(db, issue, json.loads(proposal) if isinstance(proposal, str) else proposal)
    return get_issue(issue_id, db)


@router.post("/{issue_id}/resolve", response_model=ResolutionOut)
async def resolve_issue(issue_id: int, body: ResolveRequest, db: Session = Depends(get_session)):
    issue = db.get(Issue, issue_id)
    if issue is None:
        raise HTTPException(status_code=404, detail="Issue not found")
    resolution = (
        db.query(Resolution).filter(Resolution.issue_id == issue.id).order_by(Resolution.id.desc()).first()
    )
    if resolution is None:
        raise HTTPException(status_code=400, detail="Issue has no proposed resolution to review; investigate it first")
    if body.decision is None:
        return resolution
    try:
        return ResolutionEngine().apply_human_decision(db, resolution, body.decision, body.note)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
