from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.api.deps import get_session
from app.core.config import get_settings
from app.services import llm_settings

router = APIRouter(prefix="/retrieval", tags=["retrieval"])


class RetrievalSettings(BaseModel):
    #: Results a search returns when the request does not say.
    search_top_k: int
    #: Reciprocal Rank Fusion constant: higher flattens the difference between ranks.
    search_rrf_k: int
    #: Candidates fetched per wanted result, per search leg (semantic and keyword), before fusing.
    search_candidate_multiplier: int
    #: Fragments offered to the model as numbered sources when answering a question.
    ask_top_k: int
    #: Earlier question/answer pairs of a conversation given as context to a follow-up.
    ask_history_turns: int


class RetrievalSettingsUpdate(BaseModel):
    """Only the fields sent are changed."""

    search_top_k: int | None = None
    search_rrf_k: int | None = None
    search_candidate_multiplier: int | None = None
    ask_top_k: int | None = None
    ask_history_turns: int | None = None


def _out() -> RetrievalSettings:
    s = get_settings()
    return RetrievalSettings(**{name: getattr(s, name) for name in RetrievalSettings.model_fields})


@router.get("/settings", response_model=RetrievalSettings)
def get_retrieval_settings():
    return _out()


@router.put("/settings", response_model=RetrievalSettings)
def update_retrieval_settings(body: RetrievalSettingsUpdate, db: Session = Depends(get_session)):
    updates = {n: getattr(body, n) for n in body.model_fields_set if getattr(body, n) is not None}
    try:
        llm_settings.save(db, updates)
    except llm_settings.SettingsError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return _out()
