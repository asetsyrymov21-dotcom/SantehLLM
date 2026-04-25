from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.api import deps
from app.schemas import InventoryRead, InventoryUpdate
from app.services.inventory import InventoryService

router = APIRouter(prefix="/inventory", tags=["inventory"])


@router.get("", response_model=list[InventoryRead])
def list_inventory(
    service: InventoryService = Depends(deps.get_inventory_service),
    offset: int = 0,
    limit: int = 100,
) -> list[InventoryRead]:
    return service.list(offset=offset, limit=limit)


@router.get("/{product_id}", response_model=InventoryRead)
def get_inventory(
    product_id: int,
    service: InventoryService = Depends(deps.get_inventory_service),
) -> InventoryRead:
    inv = service.get(product_id)
    if not inv:
        raise HTTPException(status_code=404, detail="Inventory not found")
    return inv


@router.patch("/{product_id}", response_model=InventoryRead)
def update_inventory(
    product_id: int,
    payload: InventoryUpdate,
    service: InventoryService = Depends(deps.get_inventory_service),
) -> InventoryRead:
    inv = service.update(product_id, payload)
    if not inv:
        raise HTTPException(status_code=404, detail="Inventory not found")
    return inv
