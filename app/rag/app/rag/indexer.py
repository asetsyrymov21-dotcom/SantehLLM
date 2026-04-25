"""
Indexing helpers for product embeddings.

Responsibilities:
- generate searchable_text for products
- (re)embed and upsert into product_embeddings
"""

from __future__ import annotations

from typing import Iterable

from sqlalchemy import insert
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.rag.embeddings import embed_texts, DEFAULT_EMBEDDING_MODEL
from app.rag.retrieval_products import build_searchable_text
from app.rag.schemas import ProductEmbedding


def index_products(
    session: Session,
    products: Iterable[object],
    *,
    tenant_id: str | None = None,
    embedding_model: str = DEFAULT_EMBEDDING_MODEL,
    batch_size: int = 64,
) -> int:
    """
    Bulk-embeds products and upserts into product_embeddings.
    Returns number of rows written.
    """
    count = 0
    buffer_products: list[object] = []
    buffer_texts: list[str] = []

    def flush() -> None:
        nonlocal count, buffer_products, buffer_texts
        if not buffer_products:
            return

        embeddings = embed_texts(buffer_texts, model=embedding_model)
        values = []
        for prod, emb, text_val in zip(buffer_products, embeddings, buffer_texts):
            pid = int(prod["id"] if isinstance(prod, dict) else getattr(prod, "id"))
            values.append(
                dict(
                    product_id=pid,
                    tenant_id=tenant_id,
                    embedding_model=embedding_model,
                    embedding=emb,
                    searchable_text=text_val,
                )
            )

        # Prefer ON CONFLICT for Postgres; fallback to bulk_save_objects otherwise.
        try:
            stmt = (
                pg_insert(ProductEmbedding)
                .values(values)
                .on_conflict_do_update(
                    index_elements=[ProductEmbedding.product_id, ProductEmbedding.tenant_id],
                    set_={
                        "embedding": pg_insert.excluded.embedding,
                        "embedding_model": pg_insert.excluded.embedding_model,
                        "searchable_text": pg_insert.excluded.searchable_text,
                        "updated_at": pg_insert.excluded.updated_at,
                    },
                )
            )
            session.execute(stmt)
        except Exception:
            session.bulk_save_objects([ProductEmbedding(**v) for v in values])

        session.flush()
        count += len(buffer_products)
        buffer_products = []
        buffer_texts = []

    for product in products:
        buffer_products.append(product)
        buffer_texts.append(build_searchable_text(product))
        if len(buffer_products) >= batch_size:
            flush()

    flush()
    return count


def reindex_product(
    session: Session,
    product: object,
    *,
    tenant_id: str | None = None,
    embedding_model: str = DEFAULT_EMBEDDING_MODEL,
) -> None:
    """Re-embed a single product."""
    index_products(
        session=session,
        products=[product],
        tenant_id=tenant_id,
        embedding_model=embedding_model,
        batch_size=1,
    )
