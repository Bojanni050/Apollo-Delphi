from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.deps import get_session
from app.core.embeddings import EmbeddingError
from app.models import Document
from app.schemas.search import SearchHitOut, SearchResponse
from app.services.search.service import SearchError, SearchService

router = APIRouter(prefix="/search", tags=["search"])


@router.get("", response_model=SearchResponse)
async def search(
    q: str = Query(..., min_length=1),
    top_k: int | None = Query(None, ge=1, le=50),
    workspace_id: int | None = Query(None, description="Search this werkmap; omitted = documents that belong to no werkmap"),
    mode: str = Query("hybrid", pattern="^(hybrid|semantic|keyword)$", description="hybrid = meaning + exact words fused (default)"),
    db: Session = Depends(get_session),
):
    scope = [r[0] for r in db.query(Document.id).filter(Document.workspace_id == workspace_id)]
    service = SearchService()
    hits = []
    # An empty scope must not fall back to searching every werkmap.
    if scope:
        try:
            hits = await service.search(db, q, top_k=top_k, document_ids=scope, mode=mode)
        except EmbeddingError as exc:
            raise HTTPException(status_code=503, detail=str(exc))
        except SearchError as exc:
            raise HTTPException(status_code=400, detail=str(exc))
    return SearchResponse(
        query=q,
        mode=service.mode_used,
        results=[SearchHitOut(**{**h.__dict__, "excerpt": h.excerpt[:600]}) for h in hits],
    )
