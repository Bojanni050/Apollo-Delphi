"""Delphi notes become oracles (doc_kind)

Revision ID: g8a3f1b2c7d4
Revises: e7f2a1c9d4b3
Create Date: 2026-10-07 10:00:00

"""
from alembic import op
import sqlalchemy as sa

revision = "g8a3f1b2c7d4"
down_revision = "e7f2a1c9d4b3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("UPDATE generated_documents SET doc_kind = 'oracle' WHERE doc_kind = 'note'")


def downgrade() -> None:
    op.execute("UPDATE generated_documents SET doc_kind = 'note' WHERE doc_kind = 'oracle'")
