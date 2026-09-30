from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, ConfigDict, Field


class WorkspaceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=256)


class WorkspaceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    created_at: dt.datetime


class WorkspaceDetailOut(WorkspaceOut):
    document_count: int = 0
    latest_analysis_run_id: int | None = None
