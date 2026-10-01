from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, Field


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    #: Ask in this werkmap; omitted = documents that belong to no werkmap.
    workspace_id: int | None = None
    #: Id of the answer this question follows up on; the earlier turns of that conversation are used as context.
    follow_up_of: int | None = None


class CitationOut(BaseModel):
    """A source fragment the answer cites; ``n`` is the number used in the answer text as [n]."""

    n: int
    chunk_id: int
    document_id: int
    document_filename: str
    page_number: int | None = None
    section: str | None = None
    line_start: int | None = None
    line_end: int | None = None
    excerpt: str
    match: str = "semantic"


class AnswerOut(BaseModel):
    id: int
    workspace_id: int | None
    #: The earlier answer this one follows up on (None for a first question).
    parent_id: int | None = None
    question: str
    #: What retrieval actually searched for when the question was a follow-up.
    standalone_question: str | None = None
    answer: str
    #: False when the documents do not answer the question.
    answered: bool
    #: False when the answer could not be tied to its sources (no valid citation, or numbers not in the sources).
    grounded: bool
    citations: list[CitationOut]
    warnings: list[str]
    sources_considered: int = 0
    search_mode: str
    model_provider: str
    model_name: str
    created_at: dt.datetime
