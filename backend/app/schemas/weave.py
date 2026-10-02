from __future__ import annotations

from pydantic import BaseModel


class WeaveDocumentOut(BaseModel):
    id: int
    filename: str
    #: The virtual folder (group), None = no group.
    group: str | None = None
    #: The type folder in the werkmap's repository (Reports, Drafts...), None while it is still in the Inbox.
    folder: str | None = None
    tags: list[str] = []


class WeaveConnectionOut(BaseModel):
    source: int
    target: int
    #: relates-to | supports | contradicts | extends
    relation: str
    why: str = ""


class WeaveOut(BaseModel):
    documents: list[WeaveDocumentOut]
    connections: list[WeaveConnectionOut]
