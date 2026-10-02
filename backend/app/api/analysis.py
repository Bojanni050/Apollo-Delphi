from __future__ import annotations

import json
import threading

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_session
from app.models import AnalysisRun, Claim, Issue
from app.schemas.common import AnalysisProgressOut, AnalysisRunOut, AnalysisStats
from app.schemas.issues import ClaimOut, IssueOut
from app.core.logging import get_logger
from app.db.session import SessionLocal
from app.services.analysis.progress import analysis_progress
from app.services.analysis.service import AnalysisService

log = get_logger(__name__)

router = APIRouter(prefix="/analysis", tags=["analysis"])


@router.post("", response_model=AnalysisRunOut, status_code=201)
def run_analysis(
    workspace_id: int | None = None,
    groups: list[str] | None = Query(None, description="Only the documents of these groups (repeat the parameter); \"__none__\" = no group"),
    background: bool = Query(False, description="Return at once with the run still running; follow it at GET /analysis/{id}/progress"),
    db: Session = Depends(get_session),
):
    service = AnalysisService()
    if background:
        if analysis_progress.running_for(workspace_id) is not None:
            raise HTTPException(status_code=409, detail="Er loopt al een analyse in deze werkmap")
        run, doc_ids = service.create_run(db, workspace_id=workspace_id, groups=groups)
        threading.Thread(target=_execute_in_background, args=(run.id, doc_ids), daemon=True, name=f"analysis-{run.id}").start()
        return _run_out(run)
    try:
        run = service.run_analysis(db, workspace_id=workspace_id, groups=groups)
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


def _execute_in_background(run_id: int, doc_ids: list[int]) -> None:
    """The analysis itself, on its own thread with its own database session. A failure is recorded on the run."""
    db = SessionLocal()
    try:
        AnalysisService().execute_run(db, run_id, doc_ids)
    except Exception:  # already written to the run and to the progress by execute_run
        log.exception("Analysis %s failed", run_id)
    finally:
        db.close()


def _run_out(run: AnalysisRun) -> AnalysisRunOut:
    return AnalysisRunOut(
        id=run.id,
        status=run.status,
        stats=AnalysisStats(**json.loads(run.stats)) if run.stats else None,
        error_message=run.error_message,
        started_at=run.started_at,
        completed_at=run.completed_at,
    )


@router.get("/running", response_model=AnalysisProgressOut | None)
def running_analysis(workspace_id: int | None = None):
    """The analysis that is running in this werkmap right now (null when none): the page picks it up again after a visit elsewhere."""
    progress = analysis_progress.running_for(workspace_id)
    return analysis_progress.snapshot(progress) if progress else None


@router.get("/{analysis_run_id}/progress", response_model=AnalysisProgressOut)
def analysis_run_progress(analysis_run_id: int, since: int = 0, db: Session = Depends(get_session)):
    """What the run is doing: stage, document, counters and the latest findings (``since`` = the last line you have seen)."""
    progress = analysis_progress.get(analysis_run_id)
    if progress is not None:
        return analysis_progress.snapshot(progress, since)
    run = db.get(AnalysisRun, analysis_run_id)  # not in memory: a run from before a restart, described by its row
    if run is None:
        raise HTTPException(status_code=404, detail="Analysis run not found")
    stats = json.loads(run.stats) if run.stats else {}
    return {
        "run_id": run.id,
        "stage": "klaar" if run.status == "completed" else "mislukt",
        "finished": run.status != "running",
        "documents_total": stats.get("documents_analyzed", 0),
        "documents_done": stats.get("documents_analyzed", 0),
        "chunks_total": 0,
        "chunks_done": 0,
        "current_document": None,
        "claims": stats.get("claims", 0),
        "open_questions": stats.get("open_questions", 0),
        "contradictions": stats.get("contradictions", 0),
        "error": run.error_message,
        "started_at": run.started_at.isoformat(),
        "feed": [],
        "last": 0,
    }


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
