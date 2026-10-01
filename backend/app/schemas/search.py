from __future__ import annotations

from pydantic import BaseModel


class SearchHitOut(BaseModel):
    chunk_id: int
    document_id: int
    document_filename: str
    excerpt: str
    page_number: int | None
    section: str | None
    line_start: int | None = None
    line_end: int | None = None
    similarity: float
    score: float = 0.0
    match: str = "semantic"  # semantic | keyword | both


class SearchResponse(BaseModel):
    query: str
    #: The mode that actually ran: hybrid falls back to keyword when the embedding endpoint is down.
    mode: str = "hybrid"
    results: list[SearchHitOut]
