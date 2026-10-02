"""pulse folders and groups: a suggested type folder and group per suggestion, the group of a document

Revision ID: a7d3e9c5b214
Revises: c3e8a1b94d27
Create Date: 2026-10-02 12:00:00
"""
from alembic import op
import sqlalchemy as sa


revision = "a7d3e9c5b214"
down_revision = "c3e8a1b94d27"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("pulse_items") as batch:
        batch.add_column(sa.Column("folder", sa.String(length=64), nullable=True))
        batch.add_column(sa.Column("group_name", sa.String(length=128), nullable=True))
    with op.batch_alter_table("documents") as batch:
        batch.add_column(sa.Column("group_name", sa.String(length=128), nullable=True))
        batch.create_index("ix_documents_group_name", ["group_name"])


def downgrade() -> None:
    with op.batch_alter_table("documents") as batch:
        batch.drop_index("ix_documents_group_name")
        batch.drop_column("group_name")
    with op.batch_alter_table("pulse_items") as batch:
        batch.drop_column("group_name")
        batch.drop_column("folder")
