from __future__ import annotations

from sqlalchemy.orm import Session

from app.repositories.product import ProductRepository
from app.schemas import SearchRequest, SearchResponse, SearchHit, ProductCard


class SearchService:
    def __init__(self, session: Session):
        self.session = session
        self.products = ProductRepository(session)

    def search_products(self, payload: SearchRequest) -> SearchResponse:
        results = self.products.search(
            query=payload.query,
            offset=payload.offset,
            limit=payload.limit,
        )
        hits = [
            SearchHit(
                id=prod.id,
                type="product",
                score=None,
                payload=ProductCard.model_validate(prod).model_dump(),
            )
            for prod in results
        ]
        return SearchResponse(total=len(hits), hits=hits)
