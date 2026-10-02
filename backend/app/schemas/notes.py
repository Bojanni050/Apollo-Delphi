from __future__ import annotations

from pydantic import BaseModel, Field


class NoteCreateRequest(BaseModel):
    """A note the user writes themselves, kept in the werkmap."""

    workspace_id: int
    title: str = Field(min_length=1, max_length=512)
    content: str = Field(default="", max_length=60000)
