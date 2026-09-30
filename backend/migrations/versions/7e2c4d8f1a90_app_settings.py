"""app_settings: runtime settings chosen in the UI (LLM provider, models, keys)

Revision ID: 7e2c4d8f1a90
Revises: 5b7d2e9a4c31
Create Date: 2026-09-30 23:00:00
"""
from alembic import op
import sqlalchemy as sa


revision = "7e2c4d8f1a90"
down_revision = "5b7d2e9a4c31"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "app_settings",
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("key"),
    )


def downgrade() -> None:
    op.drop_table("app_settings")
