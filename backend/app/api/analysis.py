from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_session
from app.models import AnalysisRun, Claim, Issue
from app.schemas.common import AnalysisRunOut, AnalysisStats
from app.schemas.issues import ClaimOut, IssueOut
from app.services.analysis.service import AnalysisService

router = APIRouter(prefix="/analysis", tags=["analysis"])


@router.post("", response_model=AnalysisRunOut, status_code=201)
def run_analysis(workspace_id: int | None = None, db: Session = Depends(get_session)):
    try:
        run = AnalysisService().run_analysis(db, workspace_id=workspace_id)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    out = AnalysisRunOut(
        id=run.id,
        status=run.status,
        stats=AnalysisStats(**json.loads(run.stats)) if run.stats else None,
        error_message=run.error_message,
        started_at=run.started_at,
        completed_at=run.completed_at,
    )
    return out


@router.get("/{analysis_run_id}", response_model=AnalysisRunOut)
def get_analysis(analysis_run_id: int, db: Session = Depends(get_session)):
    run = db.get(AnalysisRun, analysis_run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Analysis run not found")
    return AnalysisRunOut(
        id=run.id,
        status=run.status,
        stats=AnalysisStats(**json.loads(run.stats)) if run.stats else None,
        error_message=run.error_message,
        started_at=run.started_at,
        completed_at=run.completed_at,
    )


@router.get("/{analysis_run_id}/claims", response_model=list[ClaimOut])
def list_claims(analysis_run_id: int, db: Session = Depends(get_session)):
    return db.query(Claim).filter(Claim.analysis_run_id == analysis_run_id).all()


@router.get("/{analysis_run_id}/issues", response_model=list[IssueOut])
def list_analysis_issues(analysis_run_id: int, db: Session = Depends(get_session)):
    return db.query(Issue).filter(Issue.analysis_run_id == analysis_run_id).all()
