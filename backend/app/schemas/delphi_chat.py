from __future__ import annotations

import datetime as dt

from pydantic import BaseModel, Field


class DelphiChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    workspace_id: int
    #: The message this one follows; the earlier turns of that conversation are Delphi's context.
    follow_up_of: int | None = None


class DelphiMessageOut(BaseModel):
    id: int
    workspace_id: int
    parent_id: int | None
    role: str
    content: str
    refusal: str | None
    created_at: dt.datetime


class DelphiChatOut(BaseModel):
    user_message: DelphiMessageOut
    reply: DelphiMessageOut
