from __future__ import annotations

from pydantic import BaseModel


class SearchHitOut(BaseModel):
    chunk_id: int
    document_id: int
    document_filename: str
    excerpt: str
    page_number: int | None
    section: str | None
    similarity: float


class SearchResponse(BaseModel):
    query: str
    results: list[SearchHitOut]
