"""create product_embeddings (and optional document_chunks)"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

try:
    from pgvector.sqlalchemy import Vector
except Exception:  # pragma: no cover
    Vector = None

# revision identifiers, used by Alembic.
revision = "20260329_product_embeddings"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector;")

    op.create_table(
        "product_embeddings",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=True),
        sa.Column("embedding_model", sa.String(length=128), nullable=False),
        sa.Column("embedding", Vector() if Vector else sa.JSON(), nullable=False),
        sa.Column("searchable_text", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=False),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=False),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint("product_id", "tenant_id", name="uq_product_tenant_embedding"),
    )
    op.create_index(
        "ix_product_embeddings_product_tenant",
        "product_embeddings",
        ["product_id", "tenant_id"],
        unique=True,
    )

    # Optional: document chunks for KB mode
    op.create_table(
        "document_chunks",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("document_id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.String(length=64), nullable=False, index=True),
        sa.Column("embedding_model", sa.String(length=128), nullable=False),
        sa.Column("embedding", Vector() if Vector else sa.JSON(), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=False),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_document_chunks_doc_tenant",
        "document_chunks",
        ["document_id", "tenant_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_document_chunks_doc_tenant", table_name="document_chunks")
    op.drop_table("document_chunks")
    op.drop_index("ix_product_embeddings_product_tenant", table_name="product_embeddings")
    op.drop_table("product_embeddings")
