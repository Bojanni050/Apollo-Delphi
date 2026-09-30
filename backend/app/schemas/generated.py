from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, ConfigDict


class FindingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    severity: str
    finding_type: str
    statement: str | None
    evidence: str | None
    expected: str | None
    recommendation: str | None


class GeneratedDocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    status: str
    content: str | None
    outline: str | None
    verification_status: str
    revision: int
    generation_metadata: str | None
    created_at: dt.datetime
