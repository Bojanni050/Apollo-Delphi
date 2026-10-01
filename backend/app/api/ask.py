from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_session
from app.core.embeddings import EmbeddingError
from app.core.llm import LLMError
from app.models import Workspace
from app.models.qa import QAEntry
from app.schemas.ask import AnswerOut, AskRequest
from app.services.ask.service import AskService

router = APIRouter(prefix="/ask", tags=["ask"])


def _out(entry: QAEntry, sources_considered: int = 0) -> AnswerOut:
    return AnswerOut(
        id=entry.id,
        workspace_id=entry.workspace_id,
        question=entry.question,
        answer=entry.answer,
        answered=entry.answered,
        grounded=entry.grounded,
        citations=json.loads(entry.citations),
        warnings=json.loads(entry.warnings),
        sources_considered=sources_considered,
        search_mode=entry.search_mode,
        model_provider=entry.model_provider,
        model_name=entry.model_name,
        created_at=entry.created_at,
    )


@router.post("", response_model=AnswerOut, status_code=201)
async def ask(body: AskRequest, db: Session = Depends(get_session)):
    """Answer a question from the documents of one werkmap, citing the fragments used as [n]."""
    if body.workspace_id is not None and db.get(Workspace, body.workspace_id) is None:
        raise HTTPException(status_code=404, detail="Workspace not found")
    try:
        result = await AskService().ask(db, body.question, body.workspace_id)
    except (LLMError, EmbeddingError) as exc:  # EmbeddingError is an LLMError; both mean "the model is not usable"
        raise HTTPException(status_code=503, detail=str(exc))
    return _out(result.entry, result.sources_considered)


@router.get("/history", response_model=list[AnswerOut])
def history(workspace_id: int | None = None, limit: int = 50, db: Session = Depends(get_session)):
    """Earlier questions and answers of one werkmap (omitted = those that belong to no werkmap), newest first."""
    rows = (
        db.query(QAEntry)
        .filter(QAEntry.workspace_id == workspace_id)
        .order_by(QAEntry.id.desc())
        .limit(max(1, min(limit, 200)))
        .all()
    )
    return [_out(r) for r in rows]
