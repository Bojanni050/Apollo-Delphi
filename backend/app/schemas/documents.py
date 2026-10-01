from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, ConfigDict


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    workspace_id: int | None
    filename: str
    source_type: str = "upload"
    source_url: str | None = None
    repo_path: str | None = None
    title: str | None
    file_type: str
    file_size: int
    #: SHA-256 of the file: lets a client see that it is already there before uploading it again.
    content_hash: str = ""
    indexing_status: str
    error_message: str | None
    created_at: dt.datetime
    indexed_at: dt.datetime | None
    document_date: dt.date | None
