"""generated_documents: notes made from a Delphi chat (doc_kind)

Revision ID: e7f2a1c9d4b3
Revises: d9c4f2a8b6e1
Create Date: 2026-10-06 10:00:00

"""
from alembic import op
import sqlalchemy as sa

revision = "e7f2a1c9d4b3"
down_revision = "d9c4f2a8b6e1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("generated_documents") as batch:
        batch.add_column(sa.Column("doc_kind", sa.String(length=32), nullable=False, server_default="report"))


def downgrade() -> None:
    with op.batch_alter_table("generated_documents") as batch:
        batch.drop_column("doc_kind")
