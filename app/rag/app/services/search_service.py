"""
Combined search service:
- keyword/SQL search over products
- semantic product search (vector)
- optional document search for product docs/KB

Assumes a session factory (sync SQLAlchemy) is provided by the app.
"""

from __future__ import annotations

from typing import Callable, Iterable, Sequence

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.rag.retrieval_products import semantic_product_search
from app.rag.retrieval_documents import retrieve_document_chunks
from app.rag.schemas import ProductSearchHit
from app.models.product import Product  # real ORM model


class SearchService:
    def __init__(
        self,
        session_factory: Callable[[], Session],
        *,
        keyword_fields: Sequence[str] = ("sku", "name", "brand", "category", "short_description", "description"),
    ) -> None:
        self._session_factory = session_factory
        self.keyword_fields = keyword_fields

    # --- Public API ---
    def search_products(
        self,
        query: str,
        *,
        limit: int = 10,
        tenant_id: str | None = None,
    ) -> list[dict]:
        """
        Hybrid search:
        1) keyword SQL search
        2) semantic product search
        3) merge + deduplicate
        """
        if not query:
            return []

        with self._session_factory() as session:
            keyword_hits = self._keyword_product_search(
                session, query=query, limit=limit, tenant_id=tenant_id
            )
            semantic_hits = semantic_product_search(
                session, query=query, tenant_id=tenant_id, limit=limit
            )

            combined = self._merge_hits(
                session,
                keyword_hits=keyword_hits,
                semantic_hits=semantic_hits,
                limit=limit,
            )
            return combined

    def semantic_product_search(
        self, query: str, *, limit: int = 5, tenant_id: str | None = None
    ) -> list[ProductSearchHit]:
        with self._session_factory() as session:
            return semantic_product_search(
                session=session, query=query, limit=limit, tenant_id=tenant_id
            )

    def search_product_docs(
        self,
        query: str,
        *,
        tenant_id: str,
        document_id: int | None = None,
        limit: int = 5,
    ):
        with self._session_factory() as session:
            return retrieve_document_chunks(
                session=session,
                query=query,
                tenant_id=tenant_id,
                document_id=document_id,
                top_k=limit,
            )

    # --- Internals ---
    def _keyword_product_search(
        self,
        session: Session,
        *,
        query: str,
        limit: int,
        tenant_id: str | None,
    ) -> list[ProductSearchHit]:
        """
        Basic ILIKE search; adapt to project's full-text layer if available.
        """
        filters = []
        for field in self.keyword_fields:
            col = getattr(Product, field, None)
            if col is not None:
                filters.append(col.ilike(f"%{query}%"))

        if not filters:
            return []

        stmt = select(Product).where(or_(*filters))
        if hasattr(Product, "tenant_id") and tenant_id is not None:
            stmt = stmt.where(Product.tenant_id == tenant_id)

        stmt = stmt.limit(limit)
        rows = session.execute(stmt).scalars().all()

        hits: list[ProductSearchHit] = []
        for row in rows:
            searchable = " ".join(
                str(getattr(row, f, "") or "") for f in self.keyword_fields if hasattr(row, f)
            )
            hits.append(
                ProductSearchHit(
                    product_id=int(getattr(row, "id")),
                    score=1.0,  # keyword hits come first, but will be merged
                    searchable_text=searchable,
                    source="keyword",
                )
            )
        return hits

    def _merge_hits(
        self,
        session: Session,
        *,
        keyword_hits: list[ProductSearchHit],
        semantic_hits: list[ProductSearchHit],
        limit: int,
    ) -> list[dict]:
        """
        Combine keyword + semantic hits, keep Product objects and scoring metadata.
        """
        by_id: dict[int, ProductSearchHit] = {}

        for h in keyword_hits:
            by_id[h.product_id] = h

        for h in semantic_hits:
            if h.product_id in by_id:
                # blend scores (keyword priority slight boost)
                existing = by_id[h.product_id]
                existing.score = max(existing.score, h.score * 0.9 + 0.1)
                existing.source = "hybrid"
            else:
                by_id[h.product_id] = h

        if not by_id:
            return []

        ordered_ids = [
            pid
            for pid, _ in sorted(
                by_id.items(), key=lambda item: item[1].score, reverse=True
            )
        ][:limit]

        stmt = select(Product).where(Product.id.in_(ordered_ids))
        products = {p.id: p for p in session.execute(stmt).scalars().all()}

        results: list[dict] = []
        for pid in ordered_ids:
            if pid not in products:
                continue
            hit = by_id[pid]
            prod = products[pid]
            results.append(
                {
                    "product": prod,
                    "score": hit.score,
                    "match_type": hit.source,
                }
            )

        return results
