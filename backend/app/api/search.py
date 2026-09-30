from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_session
from app.schemas.search import SearchHitOut, SearchResponse
from app.services.search.service import SearchService

router = APIRouter(prefix="/search", tags=["search"])


@router.get("", response_model=SearchResponse)
async def search(
    q: str = Query(..., min_length=1),
    top_k: int | None = Query(None, ge=1, le=50),
    db: Session = Depends(get_session),
):
    hits = await SearchService().search(db, q, top_k=top_k)
    return SearchResponse(
        query=q,
        results=[SearchHitOut(**{**h.__dict__, "excerpt": h.excerpt[:600]}) for h in hits],
    )
