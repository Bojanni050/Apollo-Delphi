from __future__ import annotations

import datetime as dt

from pydantic import BaseModel


class AnalysisStats(BaseModel):
    documents_analyzed: int = 0
    claims: int = 0
    open_questions: int = 0
    contradictions: int = 0
    #: The groups the run was limited to; None = every document.
    groups: list[str] | None = None


class AnalysisFeedOut(BaseModel):
    n: int
    at: str
    #: document | claim | question | contradiction | stage
    kind: str
    text: str


class AnalysisProgressOut(BaseModel):
    """What a running analysis is doing: for the page to show while it works."""

    run_id: int
    #: start | lezen | opslaan | vergelijken | klaar | mislukt
    stage: str
    finished: bool
    documents_total: int = 0
    documents_done: int = 0
    chunks_total: int = 0
    chunks_done: int = 0
    current_document: str | None = None
    claims: int = 0
    open_questions: int = 0
    contradictions: int = 0
    error: str | None = None
    started_at: str
    feed: list[AnalysisFeedOut] = []
    #: The number of the last line of the feed; ask for ``since=last`` next time.
    last: int = 0


class AnalysisRunOut(BaseModel):
    id: int
    status: str
    stats: AnalysisStats | None = None
    error_message: str | None = None
    started_at: dt.datetime
    completed_at: dt.datetime | None
