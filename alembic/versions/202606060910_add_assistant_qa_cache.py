"""add assistant qa cache"""

from alembic import op
import sqlalchemy as sa

revision = "202606060910"
down_revision = "202603301300"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "assistant_qa_cache",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("normalized_question", sa.String(length=512), nullable=False),
        sa.Column("raw_question_example", sa.Text(), nullable=False),
        sa.Column("intent", sa.String(length=64), nullable=False),
        sa.Column("answer_text", sa.Text(), nullable=False),
        sa.Column("source_product_ids", sa.JSON(), nullable=True),
        sa.Column("source_document_ids", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="draft"),
        sa.Column("hit_count", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("meta_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("normalized_question", name="uq_assistant_qa_cache_normalized_question"),
    )
    op.create_index("ix_assistant_qa_cache_status", "assistant_qa_cache", ["status"])
    op.create_index("ix_assistant_qa_cache_intent", "assistant_qa_cache", ["intent"])
    op.create_index("ix_assistant_qa_cache_last_used", "assistant_qa_cache", ["last_used_at"])


def downgrade() -> None:
    op.drop_index("ix_assistant_qa_cache_last_used", table_name="assistant_qa_cache")
    op.drop_index("ix_assistant_qa_cache_intent", table_name="assistant_qa_cache")
    op.drop_index("ix_assistant_qa_cache_status", table_name="assistant_qa_cache")
    op.drop_table("assistant_qa_cache")
