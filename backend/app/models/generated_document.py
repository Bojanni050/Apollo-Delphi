from __future__ import annotations

import datetime as dt

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class GeneratedDocument(Base):
    __tablename__ = "generated_documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="drafting")
    outline: Mapped[str | None] = mapped_column(Text, nullable=True)
    content: Mapped[str | None] = mapped_column(Text, nullable=True)
    verification_status: Mapped[str] = mapped_column(String(32), default="pending")
    revision: Mapped[int] = mapped_column(Integer, default=0)
    generation_metadata: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    verification_findings: Mapped[list["VerificationFinding"]] = relationship(
        back_populates="generated_document", cascade="all, delete-orphan"
    )


class VerificationFinding(Base):
    __tablename__ = "verification_findings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    generated_document_id: Mapped[int] = mapped_column(
        ForeignKey("generated_documents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    finding_type: Mapped[str] = mapped_column(String(64), nullable=False)
    statement: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence: Mapped[str | None] = mapped_column(Text, nullable=True)
    expected: Mapped[str | None] = mapped_column(Text, nullable=True)
    recommendation: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    generated_document = relationship("GeneratedDocument", back_populates="verification_findings")
