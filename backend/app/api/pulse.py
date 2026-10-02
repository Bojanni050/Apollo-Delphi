from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_session
from app.core.llm import LLMError
from app.models import Document, Workspace
from app.models.pulse import PulseItem, PulseRun
from app.schemas.pulse import PulseDecideAllOut, PulseDecision, PulseItemOut, PulseResultOut, PulseRunOut
from app.services.pulse.service import PulseError, PulseService
from app.services.workspace_repo import TYPE_FOLDERS

router = APIRouter(tags=["pulse"])


def _item_out(item: PulseItem, names: dict[int, str]) -> PulseItemOut:
    connections = [{**c, "filename": names.get(c["document_id"])} for c in json.loads(item.connections)]
    return PulseItemOut(
        id=item.id,
        run_id=item.run_id,
        document_id=item.document_id,
        filename=names.get(item.document_id, ""),
        summary=item.summary,
        tags=json.loads(item.tags),
        connections=connections,
        confidence=item.confidence,
        decision=item.decision,
        folder=item.folder,
        folder_is_new=bool(item.folder) and item.folder not in TYPE_FOLDERS,
        group=item.group_name,
    )


def _names(db: Session, workspace_id: int) -> dict[int, str]:
    return {i: n for i, n in db.query(Document.id, Document.filename).filter(Document.workspace_id == workspace_id)}


def _workspace(db: Session, workspace_id: int) -> Workspace:
    ws = db.get(Workspace, workspace_id)
    if ws is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    return ws


@router.post("/workspaces/{workspace_id}/pulse", response_model=PulseResultOut, status_code=201)
async def run_pulse(workspace_id: int, force: bool = False, db: Session = Depends(get_session)):
    ws = _workspace(db, workspace_id)
    try:
        run = await PulseService().run(db, ws, force=force)
    except LLMError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    items = db.query(PulseItem).filter(PulseItem.run_id == run.id).order_by(PulseItem.id).all()
    names = _names(db, workspace_id)
    return PulseResultOut(run=PulseRunOut.model_validate(run), items=[_item_out(i, names) for i in items])


@router.get("/workspaces/{workspace_id}/pulse", response_model=PulseResultOut)
def get_pulse(workspace_id: int, db: Session = Depends(get_session)):
    """Latest run plus every suggestion still awaiting a decision (across runs)."""
    _workspace(db, workspace_id)
    run = db.query(PulseRun).filter(PulseRun.workspace_id == workspace_id).order_by(PulseRun.id.desc()).first()
    items = (
        db.query(PulseItem)
        .filter(PulseItem.workspace_id == workspace_id, PulseItem.decision == "pending")
        .order_by(PulseItem.id)
        .all()
    )
    names = _names(db, workspace_id)
    return PulseResultOut(run=PulseRunOut.model_validate(run) if run else None, items=[_item_out(i, names) for i in items])


@router.post("/workspaces/{workspace_id}/pulse/decision", response_model=PulseDecideAllOut)
def decide_all_pulse_items(workspace_id: int, body: PulseDecision, db: Session = Depends(get_session)):
    """Accept or dismiss every suggestion of this werkmap that still awaits a decision."""
    _workspace(db, workspace_id)
    try:
        decided = PulseService().decide_all(db, workspace_id, body.decision)
    except PulseError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return PulseDecideAllOut(decision=body.decision, decided=decided)


@router.post("/pulse/items/{item_id}/decision", response_model=PulseItemOut)
def decide_pulse_item(item_id: int, body: PulseDecision, db: Session = Depends(get_session)):
    item = db.get(PulseItem, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Pulse item not found")
    try:
        item = PulseService().decide(db, item, body.decision)
    except PulseError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return _item_out(item, _names(db, item.workspace_id))
