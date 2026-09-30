from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_session
from app.models import AnalysisRun, Document, Workspace
from app.schemas.workspaces import CommitOut, WorkspaceCreate, WorkspaceDetailOut, WorkspaceOut
from app.services import workspace_repo

router = APIRouter(prefix="/workspaces", tags=["workspaces"])


def _detail(db: Session, ws: Workspace) -> WorkspaceDetailOut:
    doc_count = db.query(Document).filter(Document.workspace_id == ws.id).count()
    latest_run = (
        db.query(AnalysisRun)
        .filter(AnalysisRun.workspace_id == ws.id)
        .order_by(AnalysisRun.id.desc())
        .first()
    )
    return WorkspaceDetailOut(
        id=ws.id,
        name=ws.name,
        working_dir=ws.working_dir,
        created_at=ws.created_at,
        document_count=doc_count,
        latest_analysis_run_id=latest_run.id if latest_run else None,
    )


@router.get("", response_model=list[WorkspaceOut])
def list_workspaces(db: Session = Depends(get_session)):
    return db.query(Workspace).order_by(Workspace.created_at.desc()).all()


@router.post("", response_model=WorkspaceOut, status_code=201)
def create_workspace(body: WorkspaceCreate, db: Session = Depends(get_session)):
    ws = Workspace(name=body.name.strip())
    db.add(ws)
    db.flush()  # need the id for the default folder name
    if body.working_dir:
        target = Path(body.working_dir).expanduser()
        if not target.is_absolute():
            db.rollback()
            raise HTTPException(status_code=400, detail="working_dir must be an absolute path")
    else:
        target = workspace_repo.default_working_dir(ws.id, ws.name)
    try:
        ws.working_dir = str(workspace_repo.init_repo(target))
    except (OSError, workspace_repo.GitError) as exc:
        db.rollback()
        raise HTTPException(status_code=503, detail=f"Could not set up the werkmap repository: {exc}")
    db.commit()
    db.refresh(ws)
    return ws


@router.get("/{workspace_id}/history", response_model=list[CommitOut])
def workspace_history(workspace_id: int, limit: int = 50, db: Session = Depends(get_session)):
    ws = db.get(Workspace, workspace_id)
    if ws is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    if not ws.working_dir:
        return []
    return workspace_repo.history(Path(ws.working_dir), limit=max(1, min(limit, 200)))


@router.get("/{workspace_id}", response_model=WorkspaceDetailOut)
def get_workspace(workspace_id: int, db: Session = Depends(get_session)):
    ws = db.get(Workspace, workspace_id)
    if ws is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    return _detail(db, ws)


@router.delete("/{workspace_id}", status_code=204)
def delete_workspace(workspace_id: int, db: Session = Depends(get_session)):
    ws = db.get(Workspace, workspace_id)
    if ws is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    db.delete(ws)
    db.commit()
