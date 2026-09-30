"""generated_documents.workspace_id: a generated document belongs to a werkmap

Revision ID: c5a2f9d41b68
Revises: b3d8e1f07a52
Create Date: 2026-10-01 10:30:00

Existing rows are attached to the werkmap their analysis ran on (analysis_run_id is recorded in
generation_metadata); rows whose run cannot be determined stay unassigned (NULL).
"""
import json

from alembic import op
import sqlalchemy as sa


revision = "c5a2f9d41b68"
down_revision = "b3d8e1f07a52"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("generated_documents") as batch:
        batch.add_column(sa.Column("workspace_id", sa.Integer(), nullable=True))
        batch.create_index("ix_generated_documents_workspace_id", ["workspace_id"])
        batch.create_foreign_key(
            "fk_generated_documents_workspace_id", "workspaces", ["workspace_id"], ["id"], ondelete="CASCADE"
        )

    bind = op.get_bind()
    runs = {r[0]: r[1] for r in bind.execute(sa.text("SELECT id, workspace_id FROM analysis_runs"))}
    for doc_id, meta in bind.execute(sa.text("SELECT id, generation_metadata FROM generated_documents")).fetchall():
        try:
            run_id = json.loads(meta or "{}").get("analysis_run_id")
        except ValueError:
            continue
        workspace_id = runs.get(run_id)
        if workspace_id is not None:
            bind.execute(
                sa.text("UPDATE generated_documents SET workspace_id = :w WHERE id = :i"),
                {"w": workspace_id, "i": doc_id},
            )


def downgrade() -> None:
    with op.batch_alter_table("generated_documents") as batch:
        batch.drop_constraint("fk_generated_documents_workspace_id", type_="foreignkey")
        batch.drop_index("ix_generated_documents_workspace_id")
        batch.drop_column("workspace_id")
