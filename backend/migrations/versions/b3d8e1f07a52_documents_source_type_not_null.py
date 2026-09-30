"""documents.source_type: NOT NULL, as the model says

Revision ID: b3d8e1f07a52
Revises: 9a4f6b3c2e71
Create Date: 2026-10-01 09:30:00

The GitHub-source migration (b6861c4fa3ad) added the column as nullable with a server default,
while the model declares it non-null. Rows written before that migration, or by anything that
bypassed the ORM default, could therefore hold NULL. Backfill them with 'upload' (the only kind
of document that existed before GitHub sources) and enforce the constraint.
"""
from alembic import op
import sqlalchemy as sa


revision = "b3d8e1f07a52"
down_revision = "9a4f6b3c2e71"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("UPDATE documents SET source_type = 'upload' WHERE source_type IS NULL")
    with op.batch_alter_table("documents") as batch:  # batch: SQLite cannot ALTER a column in place
        batch.alter_column(
            "source_type",
            existing_type=sa.String(length=32),
            nullable=False,
            existing_server_default="upload",
        )


def downgrade() -> None:
    with op.batch_alter_table("documents") as batch:
        batch.alter_column(
            "source_type",
            existing_type=sa.String(length=32),
            nullable=True,
            existing_server_default="upload",
        )
