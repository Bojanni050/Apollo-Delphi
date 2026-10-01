"""chunk line range: line_start / line_end on document_chunks

Revision ID: a1c9e5d73b24
Revises: f6c1d2e8a407
Create Date: 2026-10-01 18:00:00

Lets a citation point at the lines a chunk covers instead of only its page or section. Existing
chunks stay NULL until their document is re-indexed; that is cheap, because unchanged chunks keep
their embedding.
"""
from alembic import op
import sqlalchemy as sa


revision = "a1c9e5d73b24"
down_revision = "f6c1d2e8a407"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("document_chunks", sa.Column("line_start", sa.Integer(), nullable=True))
    op.add_column("document_chunks", sa.Column("line_end", sa.Integer(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("document_chunks") as batch:
        batch.drop_column("line_end")
        batch.drop_column("line_start")
