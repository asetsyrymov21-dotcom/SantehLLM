from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field


class ProductBase(BaseModel):
    sku: str = Field(..., max_length=64)
    name: str = Field(..., max_length=255)
    brand: Optional[str] = Field(default=None, max_length=255)
    category: Optional[str] = Field(default=None, max_length=255)
    unit: Optional[str] = Field(default=None, max_length=32)
    price: Optional[float] = None
    currency: Optional[str] = Field(default=None, max_length=3)
    description: Optional[str] = None
    attributes_json: Optional[dict[str, Any]] = None
    is_active: bool = True


class ProductCreate(ProductBase):
    pass


class ProductUpdate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=255)
    brand: Optional[str] = Field(default=None, max_length=255)
    category: Optional[str] = Field(default=None, max_length=255)
    unit: Optional[str] = Field(default=None, max_length=32)
    price: Optional[float] = None
    currency: Optional[str] = Field(default=None, max_length=3)
    description: Optional[str] = None
    attributes_json: Optional[dict[str, Any]] = None
    is_active: Optional[bool] = None


class ProductRead(ProductBase):
    id: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ProductCard(BaseModel):
    id: int
    sku: str
    name: str
    brand: Optional[str]
    category: Optional[str]
    price: Optional[float]
    currency: Optional[str]

    model_config = {"from_attributes": True}


__all__ = ["ProductCreate", "ProductUpdate", "ProductRead", "ProductCard"]
