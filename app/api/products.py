from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.api import deps
from app.schemas import ProductCreate, ProductRead, ProductUpdate, ProductCard
from app.services.product import ProductService

router = APIRouter(prefix="/products", tags=["products"])


@router.get("", response_model=list[ProductCard])
def list_products(
    service: ProductService = Depends(deps.get_product_service),
    query: str | None = None,
    offset: int = 0,
    limit: int = 100,
) -> list[ProductCard]:
    if query:
        return service.search(query=query, offset=offset, limit=limit)
    return service.list(offset=offset, limit=limit)


@router.get("/{product_id}", response_model=ProductRead)
def get_product(
    product_id: int,
    service: ProductService = Depends(deps.get_product_service),
) -> ProductRead:
    product = service.get(product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return product


@router.post("", response_model=ProductRead, status_code=201)
def create_product(
    payload: ProductCreate,
    service: ProductService = Depends(deps.get_product_service),
) -> ProductRead:
    return service.create(payload)


@router.patch("/{product_id}", response_model=ProductRead)
def update_product(
    product_id: int,
    payload: ProductUpdate,
    service: ProductService = Depends(deps.get_product_service),
) -> ProductRead:
    product = service.update(product_id, payload)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return product
