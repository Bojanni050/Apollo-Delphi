"""full-text index on document_chunks.content for the keyword leg of hybrid search

Revision ID: e4b7c1a9d035
Revises: d8e3a7b1c926
Create Date: 2026-10-01 14:00:00

A GIN expression index on to_tsvector('simple', content): language-neutral (no stemming), so exact
tokens such as amounts, names and identifiers match. It is an expression index, so no column is added
and the model is unchanged. PostgreSQL only; SQLite uses an in-memory BM25 instead.
"""
from alembic import op


revision = "e4b7c1a9d035"
down_revision = "d8e3a7b1c926"
branch_labels = None
depends_on = None

INDEX = "ix_document_chunks_content_fts"


def upgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute(f"CREATE INDEX IF NOT EXISTS {INDEX} ON document_chunks USING gin (to_tsvector('simple', content))")


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute(f"DROP INDEX IF EXISTS {INDEX}")
