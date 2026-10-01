from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, ConfigDict, Field


class WorkspaceCreate(BaseModel):
    name: str = Field(min_length=1, max_length=256)
    working_dir: str | None = Field(default=None, max_length=1024)


class WorkspaceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    working_dir: str | None = None
    created_at: dt.datetime


class WorkspaceDetailOut(WorkspaceOut):
    document_count: int = 0
    latest_analysis_run_id: int | None = None


class CommitOut(BaseModel):
    sha: str
    author: str
    date: str
    message: str


class UnassignedOut(BaseModel):
    """What currently belongs to no werkmap."""

    documents: int
    analysis_runs: int
    generated_documents: int


class NotMirroredOut(BaseModel):
    document_id: int
    filename: str
    reason: str


class AdoptResultOut(BaseModel):
    documents: int
    analysis_runs: int
    generated_documents: int
    mirrored_to_repository: int
    not_mirrored: list[NotMirroredOut]
