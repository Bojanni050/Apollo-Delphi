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


class AnalysisRunOut(BaseModel):
    id: int
    status: str
    stats: AnalysisStats | None = None
    error_message: str | None = None
    started_at: dt.datetime
    completed_at: dt.datetime | None
