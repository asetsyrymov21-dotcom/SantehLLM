from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class InventoryRead(BaseModel):
    product_id: int
    stock_doc: float
    stock_fact: float
    reserved_qty: float
    updated_at: datetime

    model_config = {"from_attributes": True}


class InventoryUpdate(BaseModel):
    stock_doc: Optional[float] = None
    stock_fact: Optional[float] = None
    reserved_qty: Optional[float] = None


class StockImportSource(BaseModel):
    """Metadata about stock import source."""

    source_name: str = "frap_stock_excel"
    source_file: str
    imported_at: datetime
    raw_value: Optional[str] = None


class InventoryWithSource(InventoryRead):
    """Inventory with import source metadata."""

    source_metadata: Optional[StockImportSource] = None


__all__ = [
    "InventoryRead",
    "InventoryUpdate",
    "StockImportSource",
    "InventoryWithSource",
]
