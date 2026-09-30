"""delphi pulse: pulse_runs, pulse_items

Revision ID: 5b7d2e9a4c31
Revises: 3f1a9c2b7d10
Create Date: 2026-09-30 22:00:00
"""
from alembic import op
import sqlalchemy as sa


revision = "5b7d2e9a4c31"
down_revision = "3f1a9c2b7d10"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "pulse_runs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("workspace_id", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=False),
        sa.Column("stats", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_pulse_runs_workspace_id", "pulse_runs", ["workspace_id"])
    op.create_table(
        "pulse_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("run_id", sa.Integer(), nullable=False),
        sa.Column("workspace_id", sa.Integer(), nullable=False),
        sa.Column("document_id", sa.Integer(), nullable=False),
        sa.Column("content_hash", sa.String(length=64), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("tags", sa.Text(), nullable=False),
        sa.Column("connections", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("decision", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["pulse_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_pulse_items_run_id", "pulse_items", ["run_id"])
    op.create_index("ix_pulse_items_workspace_id", "pulse_items", ["workspace_id"])
    op.create_index("ix_pulse_items_document_id", "pulse_items", ["document_id"])


def downgrade() -> None:
    op.drop_table("pulse_items")
    op.drop_table("pulse_runs")
