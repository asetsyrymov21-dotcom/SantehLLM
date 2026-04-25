from __future__ import annotations

from typing import Iterable, Sequence

from sqlalchemy import select, or_
from sqlalchemy.orm import Session

from app.db import models
from app.schemas import ProductCreate, ProductUpdate

import re


def _is_suspicious_product_name(name: str | None) -> bool:
    if not name:
        return True

    text = re.sub(r"\s+", " ", name).strip()
    text_lower = text.lower()

    if len(text) < 3:
        return True

    if len(text) > 120:
        return True

    bad_markers = [
        "каталог",
        "новинки",
        "стр.",
        "page",
        "www.",
        "http",
    ]
    if any(marker in text_lower for marker in bad_markers):
        return True

    bad_garbled_markers = ["╤", "Ё", "Є", "√", "№", "ё"]
    garbled_hits = sum(text.count(ch) for ch in bad_garbled_markers)
    if garbled_hits >= 3:
        return True

    sku_hits = re.findall(
        r"\b[A-Z]{1,3}\d{2,5}(?:-\d{1,3}[A-Z0-9]?)?\b",
        text,
        flags=re.IGNORECASE,
    )
    if len(sku_hits) >= 3:
        return True

    digits_count = len(re.findall(r"\d", text))
    if digits_count > 20:
        return True

    return False


def _should_replace_product_name(old_name: str | None, new_name: str | None) -> bool:
    if not new_name:
        return False

    if _is_suspicious_product_name(new_name):
        return False

    if not old_name:
        return True

    if _is_suspicious_product_name(old_name):
        return True

    old_clean = re.sub(r"\s+", " ", old_name).strip()
    new_clean = re.sub(r"\s+", " ", new_name).strip()

    if new_clean == old_clean:
        return False

    if len(new_clean) > len(old_clean):
        return True

    return False


class ProductRepository:
    def __init__(self, session: Session):
        self.session = session

    def get(self, product_id: int) -> models.Product | None:
        return self.session.get(models.Product, product_id)

    def get_by_sku(self, sku: str) -> models.Product | None:
        stmt = select(models.Product).where(models.Product.sku == sku)
        return self.session.scalar(stmt)

    def list(self, *, offset: int = 0, limit: int = 100) -> Sequence[models.Product]:
        stmt = select(models.Product).offset(offset).limit(limit)
        return self.session.scalars(stmt).all()

    def search(
        self,
        query: str,
        *,
        brand: str | None = None,
        category: str | None = None,
        offset: int = 0,
        limit: int = 20,
    ) -> Sequence[models.Product]:
        pattern = f"%{query}%"
        conditions = [
            or_(
                models.Product.sku.ilike(pattern),
                models.Product.name.ilike(pattern),
                models.Product.brand.ilike(pattern),
                models.Product.category.ilike(pattern),
            )
        ]
        if brand:
            conditions.append(models.Product.brand.ilike(f"%{brand}%"))
        if category:
            conditions.append(models.Product.category.ilike(f"%{category}%"))
        stmt = select(models.Product).where(*conditions).offset(offset).limit(limit)
        return self.session.scalars(stmt).all()

    def create(self, data: ProductCreate) -> models.Product:
        product = models.Product(**data.model_dump())
        self.session.add(product)
        self.session.flush()
        return product

    def update(self, product: models.Product, data: ProductUpdate) -> models.Product:
        for key, value in data.model_dump(exclude_unset=True).items():
            setattr(product, key, value)
        self.session.add(product)
        self.session.flush()
        return product

    def upsert_by_sku(self, data: ProductCreate) -> tuple[models.Product, bool]:
        existing = self.get_by_sku(data.sku)

        if existing:
            patch: dict = {}

            if _should_replace_product_name(existing.name, data.name):
                patch["name"] = data.name

            if data.brand and not existing.brand:
                patch["brand"] = data.brand

            if data.category and not existing.category:
                patch["category"] = data.category

            if data.unit and not existing.unit:
                patch["unit"] = data.unit

            if data.price is not None:
                patch["price"] = data.price

            if data.currency and not existing.currency:
                patch["currency"] = data.currency

            if data.description:
                if not existing.description or len(data.description) > len(
                    existing.description
                ):
                    patch["description"] = data.description

            old_attrs = existing.attributes_json or {}
            new_attrs = data.attributes_json or {}
            merged_attrs = {**old_attrs, **new_attrs}
            patch["attributes_json"] = merged_attrs

            if data.is_active is not None:
                patch["is_active"] = data.is_active

            if patch:
                update_data = ProductUpdate(**patch)
                self.update(existing, update_data)

            return existing, False

        created = self.create(data)
        return created, True

    def delete(self, product: models.Product) -> None:
        self.session.delete(product)

    def bulk_get_by_ids(self, ids: Iterable[int]) -> Sequence[models.Product]:
        stmt = select(models.Product).where(models.Product.id.in_(list(ids)))
        return self.session.scalars(stmt).all()
