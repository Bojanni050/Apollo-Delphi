from __future__ import annotations

import datetime as dt

from sqlalchemy import DateTime, ForeignKey, Integer, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class DelphiChatMessage(Base):
    """One turn of a conversation with Delphi, the chat agent of a werkmap.

    A conversation is the chain of parents: every message points at the one it
    follows. Delphi answers only about the documents of that one werkmap and
    about Apollo itself; a message that falls outside that scope is refused
    politely instead of answered.
    """

    __tablename__ = "delphi_chat_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    workspace_id: Mapped[int] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True)
    #: The message this one follows; the chain of parents is the conversation.
    parent_id: Mapped[int | None] = mapped_column(
        ForeignKey("delphi_chat_messages.id", ondelete="CASCADE"), nullable=True, index=True
    )
    role: Mapped[str] = mapped_column(Text)  # "user" or "delphi"
    content: Mapped[str] = mapped_column(Text)
    #: Why Delphi did not answer: "out_of_scope" (outside the werkmap and Apollo) or "no_documents".
    refusal: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
