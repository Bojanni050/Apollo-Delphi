"""werkmap is a repository: workspaces.working_dir, documents.inbox_path

Revision ID: 3f1a9c2b7d10
Revises: b6861c4fa3ad
Create Date: 2026-09-30 21:30:00
"""
from alembic import op
import sqlalchemy as sa


revision = '3f1a9c2b7d10'
down_revision = 'b6861c4fa3ad'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('workspaces', sa.Column('working_dir', sa.String(length=1024), nullable=True))
    op.add_column('documents', sa.Column('inbox_path', sa.String(length=1024), nullable=True))


def downgrade() -> None:
    op.drop_column('documents', 'inbox_path')
    op.drop_column('workspaces', 'working_dir')
