from __future__ import annotations

from typing import Sequence

from sqlalchemy.orm import Session

from app.db import models
from app.repositories.product import ProductRepository
from app.schemas import ProductCreate, ProductRead, ProductUpdate, ProductCard


class ProductService:
    def __init__(self, session: Session):
        self.session = session
        self.repo = ProductRepository(session)

    def list(self, offset: int = 0, limit: int = 100) -> list[ProductCard]:
        products: Sequence[models.Product] = self.repo.list(offset=offset, limit=limit)
        return [ProductCard.model_validate(p) for p in products]

    def search(
        self,
        query: str,
        *,
        brand: str | None = None,
        category: str | None = None,
        offset: int = 0,
        limit: int = 20,
    ) -> list[ProductCard]:
        products = self.repo.search(
            query=query, brand=brand, category=category, offset=offset, limit=limit
        )
        return [ProductCard.model_validate(p) for p in products]

    def get(self, product_id: int) -> ProductRead | None:
        product = self.repo.get(product_id)
        if product:
            return ProductRead.model_validate(product)
        return None

    def create(self, payload: ProductCreate) -> ProductRead:
        product = self.repo.create(payload)
        self.session.commit()
        return ProductRead.model_validate(product)

    def update(self, product_id: int, payload: ProductUpdate) -> ProductRead | None:
        product = self.repo.get(product_id)
        if not product:
            return None
        updated = self.repo.update(product, payload)
        self.session.commit()
        return ProductRead.model_validate(updated)
