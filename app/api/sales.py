from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.api import deps
from app.schemas import SaleCreate, SaleRead
from app.services.sales import SalesService

router = APIRouter(prefix="/sales", tags=["sales"])


@router.post("", response_model=SaleRead, status_code=201)
def create_sale(
    payload: SaleCreate,
    service: SalesService = Depends(deps.get_sales_service),
) -> SaleRead:
    return service.create(payload)


@router.get("/{sale_id}", response_model=SaleRead)
def get_sale(
    sale_id: int,
    service: SalesService = Depends(deps.get_sales_service),
) -> SaleRead:
    sale = service.get(sale_id)
    if not sale:
        raise HTTPException(status_code=404, detail="Sale not found")
    return sale


@router.post("/{sale_id}/confirm", response_model=SaleRead)
def confirm_sale(
    sale_id: int,
    service: SalesService = Depends(deps.get_sales_service),
) -> SaleRead:
    try:
        return service.confirm(sale_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/{sale_id}/cancel", response_model=SaleRead)
def cancel_sale(
    sale_id: int,
    service: SalesService = Depends(deps.get_sales_service),
) -> SaleRead:
    try:
        return service.cancel(sale_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
