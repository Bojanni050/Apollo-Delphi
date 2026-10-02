"""delphi_chat_messages: the conversation with Delphi, the chat agent of a werkmap

Revision ID: d9c4f2a8b6e1
Revises: a7d3e9c5b214
Create Date: 2026-10-05 12:00:00

"""
from alembic import op
import sqlalchemy as sa

revision = "d9c4f2a8b6e1"
down_revision = "a7d3e9c5b214"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "delphi_chat_messages",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("workspace_id", sa.Integer(), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("parent_id", sa.Integer(), sa.ForeignKey("delphi_chat_messages.id", ondelete="CASCADE"), nullable=True),
        sa.Column("role", sa.Text(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("refusal", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_delphi_chat_messages_workspace_id", table_name="delphi_chat_messages", columns=["workspace_id"])
    op.create_index("ix_delphi_chat_messages_parent_id", table_name="delphi_chat_messages", columns=["parent_id"])


def downgrade() -> None:
    op.drop_index("ix_delphi_chat_messages_parent_id", table_name="delphi_chat_messages")
    op.drop_index("ix_delphi_chat_messages_workspace_id", table_name="delphi_chat_messages")
    op.drop_table("delphi_chat_messages")
