from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_session
from app.schemas.knowledge import KnowledgeItemOut
from app.services.knowledge.service import KnowledgeService

router = APIRouter(prefix="/knowledge", tags=["knowledge"])


@router.get("", response_model=list[KnowledgeItemOut])
def get_knowledge(
    analysis_run_id: int | None = Query(None),
    workspace_id: int | None = Query(None, description="Latest knowledge of this werkmap; omitted = no werkmap"),
    db: Session = Depends(get_session),
):
    return KnowledgeService().get_knowledge_state(db, analysis_run_id, workspace_id)


@router.post("/build", response_model=list[KnowledgeItemOut])
def build_knowledge(analysis_run_id: int = Query(...), db: Session = Depends(get_session)):
    try:
        return KnowledgeService().build_knowledge_state(db, analysis_run_id)
    except ValueError as exc:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail=str(exc))
