"""evidence line range: line_start / line_end on evidence

Revision ID: c3e8a1b94d27
Revises: b7d2f4a86c15
Create Date: 2026-10-01 22:00:00

Evidence created from now on records the lines of the uploaded text file it was taken from. Existing
evidence stays NULL; running the analysis again fills it for new runs.
"""
from alembic import op
import sqlalchemy as sa


revision = "c3e8a1b94d27"
down_revision = "b7d2f4a86c15"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("evidence", sa.Column("line_start", sa.Integer(), nullable=True))
    op.add_column("evidence", sa.Column("line_end", sa.Integer(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("evidence") as batch:
        batch.drop_column("line_end")
        batch.drop_column("line_start")
