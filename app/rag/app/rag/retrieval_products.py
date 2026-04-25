"""
Semantic retrieval for products (not document chunks).

Key points:
- Uses embeddings stored in product_embeddings
- Applies lexical rerank + diversity filtering
- Keeps tenant isolation optional
"""

from __future__ import annotations

import json
import math
from typing import Iterable, Sequence

from sqlalchemy import text, select
from sqlalchemy.orm import Session

from app.rag.embeddings import embed_texts, DEFAULT_EMBEDDING_MODEL
from app.rag.rerank import lexical_overlap, jaccard_similarity
from app.rag.schemas import ProductEmbedding, ProductSearchHit


def build_searchable_text(product: object) -> str:
    """
    Assemble searchable text from product fields.
    Works with either ORM objects (attrs) or dict-like items.
    """

    def grab(key: str) -> str:
        if isinstance(product, dict):
            return str(product.get(key, "") or "")
        return str(getattr(product, key, "") or "")

    parts = [
        grab("sku"),
        grab("name"),
        grab("brand"),
        grab("category"),
        grab("short_description"),
        grab("description"),
    ]

    attrs = grab("attributes_json")
    if attrs and attrs not in ("{}", "null", "None"):
        parts.append(attrs if isinstance(attrs, str) else json.dumps(attrs, ensure_ascii=False))

    return "\n".join(p for p in parts if p)


def _vector_candidates(
    session: Session,
    qvec: Sequence[float],
    *,
    tenant_id: str | None,
    embedding_model: str,
    limit: int,
) -> list[tuple[int, str, float]]:
    """
    Runs the raw vector search. Returns tuples (product_id, searchable_text, score).
    Uses pgvector <=> when available; otherwise falls back to Python scoring
    (dev-only, used for local tests / non-Postgres).
    """
    dialect = session.bind.dialect.name if session.bind is not None else ""

    if dialect == "postgresql":
        stmt = text(
            """
            SELECT
                product_id,
                searchable_text,
                1 - (embedding <=> :qvec) AS score
            FROM product_embeddings
            WHERE embedding_model = :embedding_model
              AND (:tenant_id IS NULL OR tenant_id = :tenant_id)
            ORDER BY embedding <=> :qvec
            LIMIT :limit;
            """
        )

        rows = session.execute(
            stmt,
            {
                "qvec": list(qvec),
                "tenant_id": tenant_id,
                "embedding_model": embedding_model,
                "limit": limit,
            },
        ).all()

        return [(r[0], r[1], float(r[2]) if r[2] is not None else 0.0) for r in rows]

    # --- Dev/test fallback (no pgvector) ---
    stmt = select(ProductEmbedding).where(ProductEmbedding.embedding_model == embedding_model)
    if tenant_id is not None:
        stmt = stmt.where(ProductEmbedding.tenant_id == tenant_id)
    rows = session.execute(stmt).scalars().all()

    def cosine(a: Sequence[float], b: Sequence[float]) -> float:
        if not a or not b or len(a) != len(b):
            return 0.0
        dot = sum(x * y for x, y in zip(a, b))
        na = math.sqrt(sum(x * x for x in a))
        nb = math.sqrt(sum(y * y for y in b))
        if na == 0 or nb == 0:
            return 0.0
        return dot / (na * nb)

    scored: list[tuple[int, str, float]] = []
    for row in rows:
        emb = row.embedding or []
        score = cosine(qvec, emb)
        scored.append((row.product_id, row.searchable_text, score))

    scored.sort(key=lambda x: x[2], reverse=True)
    return scored[:limit]


def semantic_product_search(
    session: Session,
    query: str,
    *,
    tenant_id: str | None = None,
    limit: int = 5,
    embedding_model: str = DEFAULT_EMBEDDING_MODEL,
    diversity_threshold: float = 0.6,
) -> list[ProductSearchHit]:
    """
    1) embed query
    2) vector search
    3) lexical rerank
    4) optional diversity filter
    """
    if not query:
        return []

    qvec = embed_texts([query], model=embedding_model)[0]

    # take a bit more for rerank/diversity, then trim
    raw_limit = max(limit * 3, limit + 2)
    candidates = _vector_candidates(
        session,
        qvec,
        tenant_id=tenant_id,
        embedding_model=embedding_model,
        limit=raw_limit,
    )

    if not candidates:
        return []

    max_lex = max((lexical_overlap(query, t) for _, t, _ in candidates), default=1)
    results: list[ProductSearchHit] = []

    for pid, text_value, vec_score in candidates:
        lex = lexical_overlap(query, text_value)
        norm_lex = lex / max_lex if max_lex else 0.0
        final = vec_score * 0.7 + norm_lex * 0.3
        results.append(
            ProductSearchHit(
                product_id=pid,
                score=final,
                searchable_text=text_value,
                source="semantic",
            )
        )

    # diversity: drop near-duplicates based on searchable_text similarity
    selected: list[ProductSearchHit] = []
    for r in sorted(results, key=lambda x: x.score, reverse=True):
        if any(
            jaccard_similarity(r.searchable_text, s.searchable_text)
            >= diversity_threshold
            for s in selected
        ):
            continue
        selected.append(r)
        if len(selected) >= limit:
            break

    return selected


def upsert_product_embeddings(
    session: Session,
    products: Iterable[object],
    *,
    tenant_id: str | None,
    embedding_model: str = DEFAULT_EMBEDDING_MODEL,
    batch_size: int = 64,
) -> int:
    """
    Utility used by indexer: embeds and upserts products into product_embeddings.
    Returns number of upserted rows.
    """
    buffer: list[ProductEmbedding] = []
    total = 0

    def flush() -> None:
        nonlocal total
        if not buffer:
            return
        session.bulk_save_objects(buffer)
        session.flush()
        total += len(buffer)
        buffer.clear()

    current_batch_texts: list[str] = []
    current_batch_products: list[object] = []

    for product in products:
        searchable = build_searchable_text(product)
        current_batch_texts.append(searchable)
        current_batch_products.append(product)

        if len(current_batch_texts) >= batch_size:
            embeddings = embed_texts(current_batch_texts, model=embedding_model)
            for prod, emb, text_val in zip(
                current_batch_products, embeddings, current_batch_texts
            ):
                buffer.append(
                    ProductEmbedding(
                        product_id=int(prod["id"] if isinstance(prod, dict) else getattr(prod, "id")),
                        tenant_id=tenant_id,
                        embedding_model=embedding_model,
                        embedding=emb,
                        searchable_text=text_val,
                    )
                )
            flush()
            current_batch_texts.clear()
            current_batch_products.clear()

    if current_batch_texts:
        embeddings = embed_texts(current_batch_texts, model=embedding_model)
        for prod, emb, text_val in zip(
            current_batch_products, embeddings, current_batch_texts
        ):
            buffer.append(
                ProductEmbedding(
                    product_id=int(prod["id"] if isinstance(prod, dict) else getattr(prod, "id")),
                    tenant_id=tenant_id,
                    embedding_model=embedding_model,
                    embedding=emb,
                    searchable_text=text_val,
                )
            )
        flush()

    return total
