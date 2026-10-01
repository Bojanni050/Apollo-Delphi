"""drop the duplicate workspace foreign keys left by ca82a5d7702b + b6861c4fa3ad

Revision ID: d8e3a7b1c926
Revises: c5a2f9d41b68
Create Date: 2026-10-01 12:00:00

Both earlier migrations used to create the same foreign key (`analysis_runs.workspace_id` and
`documents.workspace_id` -> `workspaces.id`, ON DELETE CASCADE), so databases created before
b6861c4fa3ad was fixed carry two identical constraints (`..._fkey` and `..._fkey1`). They are
harmless but pointless. This drops every extra one that is identical to the one it keeps.

PostgreSQL only (SQLite never had these constraints). Idempotent: a database with a single foreign
key, or none, is left alone. Nothing is dropped unless an identical constraint remains.
"""
from alembic import op
import sqlalchemy as sa


revision = "d8e3a7b1c926"
down_revision = "c5a2f9d41b68"
branch_labels = None
depends_on = None


def _workspace_fks(table: str) -> list[dict]:
    inspector = sa.inspect(op.get_bind())
    fks = [
        fk
        for fk in inspector.get_foreign_keys(table)
        if fk.get("name") and fk["referred_table"] == "workspaces" and fk["constrained_columns"] == ["workspace_id"]
    ]
    return sorted(fks, key=lambda fk: fk["name"])


def upgrade() -> None:
    if op.get_bind().dialect.name == "sqlite":
        return
    for table in ("analysis_runs", "documents"):
        fks = _workspace_fks(table)
        seen: set[tuple] = set()
        for fk in fks:
            identity = (tuple(fk["referred_columns"]), (fk.get("options") or {}).get("ondelete"))
            if identity in seen:
                op.drop_constraint(fk["name"], table, type_="foreignkey")
            else:
                seen.add(identity)


def downgrade() -> None:
    # Re-creating a duplicate constraint would only reintroduce the redundancy; nothing to undo.
    pass
