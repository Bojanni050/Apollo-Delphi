from __future__ import annotations

import datetime as dt
import json

from pydantic import BaseModel, ConfigDict, field_validator


class PulseConnectionOut(BaseModel):
    document_id: int
    filename: str | None = None
    relation: str
    why: str = ""


class PulseItemOut(BaseModel):
    id: int
    run_id: int
    document_id: int
    filename: str
    summary: str
    tags: list[str]
    connections: list[PulseConnectionOut]
    confidence: float
    decision: str
    #: Suggested type folder in the werkmap's repository, and whether it is outside the fixed list; suggested virtual group.
    folder: str | None = None
    folder_is_new: bool = False
    group: str | None = None


class PulseRunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True, protected_namespaces=())

    id: int
    workspace_id: int
    status: str
    provider: str
    model: str
    stats: dict | None = None
    error_message: str | None = None
    started_at: dt.datetime
    completed_at: dt.datetime | None = None

    @field_validator("stats", mode="before")
    @classmethod
    def _parse_stats(cls, v):
        return json.loads(v) if isinstance(v, str) else v


class PulseResultOut(BaseModel):
    run: PulseRunOut | None
    items: list[PulseItemOut]


class PulseDecision(BaseModel):
    decision: str  # accepted | dismissed


class PulseDecideAllOut(BaseModel):
    decision: str
    decided: int
