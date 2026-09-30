from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, ConfigDict


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    workspace_id: int | None
    filename: str
    title: str | None
    file_type: str
    file_size: int
    indexing_status: str
    error_message: str | None
    created_at: dt.datetime
    indexed_at: dt.datetime | None
    document_date: dt.date | None
