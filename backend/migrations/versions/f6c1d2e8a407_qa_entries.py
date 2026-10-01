"""qa_entries: questions asked in a werkmap with their cited answers

Revision ID: f6c1d2e8a407
Revises: e4b7c1a9d035
Create Date: 2026-10-01 15:00:00
"""
from alembic import op
import sqlalchemy as sa


revision = "f6c1d2e8a407"
down_revision = "e4b7c1a9d035"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "qa_entries",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("workspace_id", sa.Integer(), nullable=True),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("answer", sa.Text(), nullable=False),
        sa.Column("answered", sa.Boolean(), nullable=False),
        sa.Column("grounded", sa.Boolean(), nullable=False),
        sa.Column("citations", sa.Text(), nullable=False),
        sa.Column("warnings", sa.Text(), nullable=False),
        sa.Column("search_mode", sa.String(length=16), nullable=False),
        sa.Column("model_provider", sa.String(length=64), nullable=False),
        sa.Column("model_name", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_qa_entries_workspace_id", "qa_entries", ["workspace_id"])


def downgrade() -> None:
    op.drop_table("qa_entries")
