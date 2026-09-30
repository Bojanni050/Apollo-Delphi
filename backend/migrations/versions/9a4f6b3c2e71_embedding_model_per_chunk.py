"""embedding model per chunk: variable vector dimension, embedding_model / embedding_dim

Revision ID: 9a4f6b3c2e71
Revises: 7e2c4d8f1a90
Create Date: 2026-10-01 09:00:00

The vector column used to be VECTOR(64), which fits only the mock embedder. Real models
produce other sizes (bge-m3: 1024), so the column becomes an unconstrained VECTOR and each
chunk records the model and dimension it was embedded with. Existing vectors are marked
'legacy': search ignores them until the document is re-indexed with the active model.
"""
from alembic import op
import sqlalchemy as sa


revision = "9a4f6b3c2e71"
down_revision = "7e2c4d8f1a90"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("document_chunks", sa.Column("embedding_model", sa.String(length=128), nullable=True))
    op.add_column("document_chunks", sa.Column("embedding_dim", sa.Integer(), nullable=True))
    op.create_index("ix_document_chunks_embedding_model", "document_chunks", ["embedding_model"])
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("ALTER TABLE document_chunks ALTER COLUMN embedding TYPE vector")
        op.execute(
            "UPDATE document_chunks SET embedding_model = 'legacy', embedding_dim = vector_dims(embedding) "
            "WHERE embedding IS NOT NULL"
        )
    else:
        op.execute(
            "UPDATE document_chunks SET embedding_model = 'legacy', embedding_dim = 64 WHERE embedding IS NOT NULL"
        )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        # Only 64-dimensional vectors fit the old column; others cannot be kept.
        op.execute("UPDATE document_chunks SET embedding = NULL WHERE embedding IS NOT NULL AND vector_dims(embedding) <> 64")
        op.execute("ALTER TABLE document_chunks ALTER COLUMN embedding TYPE vector(64)")
    op.drop_index("ix_document_chunks_embedding_model", table_name="document_chunks")
    op.drop_column("document_chunks", "embedding_dim")
    op.drop_column("document_chunks", "embedding_model")
