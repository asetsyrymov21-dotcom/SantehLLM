from __future__ import annotations

import os
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from app.models.product import Product
from app.rag import indexer
from app.services.search_service import SearchService

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./app.db")
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_session() -> Session:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


router = APIRouter(prefix="/search", tags=["search"])


class SearchRequest(BaseModel):
    query: str
    limit: int = 10
    tenant_id: str | None = None


class SearchResponseItem(BaseModel):
    product_id: int
    sku: str | None
    name: str | None
    brand: str | None
    category: str | None
    short_description: str | None
    score: float
    match_type: str


@router.post("/products", response_model=list[SearchResponseItem])
def search_products(
    payload: SearchRequest,
    session: Annotated[Session, Depends(get_session)],
):
    service = SearchService(lambda: session)
    results = service.search_products(
        payload.query, limit=payload.limit, tenant_id=payload.tenant_id
    )

    resp: list[SearchResponseItem] = []
    for item in results:
        prod = item["product"]
        resp.append(
            SearchResponseItem(
                product_id=prod.id,
                sku=getattr(prod, "sku", None),
                name=getattr(prod, "name", None),
                brand=getattr(prod, "brand", None),
                category=getattr(prod, "category", None),
                short_description=getattr(prod, "short_description", None),
                score=item["score"],
                match_type=item["match_type"],
            )
        )
    return resp


@router.post("/reindex-products")
def reindex_products(
    session: Annotated[Session, Depends(get_session)],
    tenant_id: str | None = None,
):
    products = session.query(Product).all()
    if not products:
        return {"status": "no-products", "message": "Каталог пуст, индексировать нечего"}

    count = indexer.index_products(session, products, tenant_id=tenant_id)
    session.commit()
    return {"status": "ok", "indexed": count}
