"""qa_entries: follow-up questions (parent_id) and the standalone question retrieval used

Revision ID: b7d2f4a86c15
Revises: a1c9e5d73b24
Create Date: 2026-10-01 20:00:00
"""
from alembic import op
import sqlalchemy as sa


revision = "b7d2f4a86c15"
down_revision = "a1c9e5d73b24"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("qa_entries") as batch:
        batch.add_column(sa.Column("parent_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("standalone_question", sa.Text(), nullable=True))
        batch.create_foreign_key("fk_qa_entries_parent_id", "qa_entries", ["parent_id"], ["id"], ondelete="SET NULL")
        batch.create_index("ix_qa_entries_parent_id", ["parent_id"])


def downgrade() -> None:
    with op.batch_alter_table("qa_entries") as batch:
        batch.drop_index("ix_qa_entries_parent_id")
        batch.drop_constraint("fk_qa_entries_parent_id", type_="foreignkey")
        batch.drop_column("standalone_question")
        batch.drop_column("parent_id")
