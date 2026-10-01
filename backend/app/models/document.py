from __future__ import annotations

import datetime as dt

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, func, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.db.vector import vector_column


#: pending -> processing -> parsed -> indexed (or failed). A ``parsed`` document has its fragments: it can be read and is
#: searchable by words; ``indexed`` means every fragment also has a vector of the active embedding model.
READY_STATUSES = ("parsed", "indexed")


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    workspace_id: Mapped[int | None] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=True, index=True)
    filename: Mapped[str] = mapped_column(String(512))
    stored_filename: Mapped[str] = mapped_column(String(128), unique=True)
    file_type: Mapped[str] = mapped_column(String(32))
    file_size: Mapped[int] = mapped_column(Integer, default=0)
    content_hash: Mapped[str] = mapped_column(String(64), default="")
    inbox_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    title: Mapped[str | None] = mapped_column(String(512), nullable=True)
    doc_metadata: Mapped[dict] = mapped_column(Text, default="{}", nullable=True)
    indexing_status: Mapped[str] = mapped_column(String(32), default="pending")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
    indexed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    document_date: Mapped[dt.date | None] = mapped_column(nullable=True)
    source_type: Mapped[str] = mapped_column(String(32), default="upload")
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    repo_path: Mapped[str | None] = mapped_column(Text, nullable=True)

    chunks: Mapped[list[DocumentChunk]] = relationship(back_populates="document", cascade="all, delete-orphan")

    @property
    def metadata_dict(self) -> dict:
        import json

        return json.loads(self.doc_metadata or "{}")


class DocumentChunk(Base):
    __tablename__ = "document_chunks"

    __table_args__ = (
        # Keyword leg of hybrid search (see services/search/service.py). PostgreSQL only: SQLite has no
        # to_tsvector, so the index is not emitted there (and keyword search uses an in-memory BM25).
        Index(
            "ix_document_chunks_content_fts",
            text("to_tsvector('simple', content)"),
            postgresql_using="gin",
        ).ddl_if(dialect="postgresql"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id", ondelete="CASCADE"), nullable=False, index=True)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    page_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    section: Mapped[str | None] = mapped_column(String(256), nullable=True)
    #: Inclusive 1-based line range in the extracted text; NULL for chunks indexed before this existed.
    line_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    line_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[list[float] | None] = mapped_column(vector_column(None), nullable=True)
    #: Model and dimension this vector was produced with; search only compares vectors of the active model.
    embedding_model: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    embedding_dim: Mapped[int | None] = mapped_column(Integer, nullable=True)

    document: Mapped[Document] = relationship(back_populates="chunks")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
