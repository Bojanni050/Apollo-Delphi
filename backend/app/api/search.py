from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_session
from app.models import Document
from app.schemas.search import SearchHitOut, SearchResponse
from app.services.search.service import SearchService

router = APIRouter(prefix="/search", tags=["search"])


@router.get("", response_model=SearchResponse)
async def search(
    q: str = Query(..., min_length=1),
    top_k: int | None = Query(None, ge=1, le=50),
    workspace_id: int | None = Query(None, description="Search this werkmap; omitted = documents that belong to no werkmap"),
    db: Session = Depends(get_session),
):
    scope = [r[0] for r in db.query(Document.id).filter(Document.workspace_id == workspace_id)]
    # An empty scope must not fall back to searching every werkmap.
    hits = await SearchService().search(db, q, top_k=top_k, document_ids=scope) if scope else []
    return SearchResponse(
        query=q,
        results=[SearchHitOut(**{**h.__dict__, "excerpt": h.excerpt[:600]}) for h in hits],
    )
