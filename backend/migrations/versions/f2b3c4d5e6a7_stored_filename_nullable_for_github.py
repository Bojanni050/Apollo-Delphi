"""documents.stored_filename: nullable, NULL for GitHub digests

Revision ID: f2b3c4d5e6a7
Revises: e7f2a1c9d4b3
Create Date: 2026-10-15 10:00:00

Every GitHub digest used the placeholder ``"-"`` for ``stored_filename``. The column is
UNIQUE, so only one GitHub document could exist in the whole database: importing a second
repository (for instance through Codecheck) hit the unique constraint and failed. A digest
has no file on disk, so the column becomes nullable and the GitHub rows are set to NULL. A
UNIQUE column allows any number of NULLs (both PostgreSQL and SQLite), while uploads keep
their own server-generated, unique name.
"""
from alembic import op
import sqlalchemy as sa


revision = "f2b3c4d5e6a7"
down_revision = "e7f2a1c9d4b3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # First make the column nullable (PostgreSQL still enforces NOT NULL on the UPDATE otherwise), then free the
    # single "-" slot so more than one digest can exist.
    with op.batch_alter_table("documents") as batch:  # batch: SQLite cannot ALTER a column in place
        batch.alter_column("stored_filename", existing_type=sa.String(length=128), nullable=True)
    op.execute("UPDATE documents SET stored_filename = NULL WHERE source_type = 'github'")


def downgrade() -> None:
    # Best effort: a placeholder only fits one row while the column is UNIQUE, so a database with more than one
    # digest cannot be represented again. Existing uploads keep their own name.
    op.execute("UPDATE documents SET stored_filename = '-' WHERE stored_filename IS NULL")
    with op.batch_alter_table("documents") as batch:
        batch.alter_column("stored_filename", existing_type=sa.String(length=128), nullable=False)
