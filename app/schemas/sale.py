from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field

from app.db.models import SaleStatus, SourceType, DocumentStatus


class SaleItemCreate(BaseModel):
    product_id: Optional[int] = None
    product_name_snapshot: str
    sku_snapshot: Optional[str] = None
    quantity: float
    unit: Optional[str] = Field(default=None, max_length=32)
    unit_price: float
    line_total: float


class SaleCreate(BaseModel):
    sale_number: str = Field(..., max_length=64)
    sale_date: datetime
    source_type: SourceType
    status: SaleStatus
    customer_name: Optional[str] = Field(default=None, max_length=255)
    total_amount: Optional[float] = None
    currency: str = Field(..., max_length=3)
    raw_input_text: Optional[str] = None
    created_by: Optional[int] = None
    items: List[SaleItemCreate]


class SaleItemRead(BaseModel):
    id: int
    sale_id: int
    product_id: Optional[int]
    product_name_snapshot: str
    sku_snapshot: Optional[str]
    quantity: float
    unit: Optional[str]
    unit_price: float
    line_total: float

    model_config = {"from_attributes": True}


class SaleRead(BaseModel):
    id: int
    sale_number: str
    sale_date: datetime
    source_type: SourceType
    status: SaleStatus
    customer_name: Optional[str]
    total_amount: float
    currency: str
    raw_input_text: Optional[str]
    created_by: Optional[int]
    created_at: datetime
    items: List[SaleItemRead]

    model_config = {"from_attributes": True}


class DocumentRead(BaseModel):
    id: int
    document_type: str
    related_sale_id: Optional[int]
    document_number: str
    file_path: Optional[str]
    status: DocumentStatus
    created_at: datetime

    model_config = {"from_attributes": True}


__all__ = [
    "SaleItemCreate",
    "SaleCreate",
    "SaleRead",
    "SaleItemRead",
    "DocumentRead",
]
