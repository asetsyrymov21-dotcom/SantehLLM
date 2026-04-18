"""Schemas for Excel row ingestion pipeline.

Defines Pydantic models for raw and normalized Excel row representations.
"""

from typing import Any
from pydantic import BaseModel, Field


class ExcelRowRaw(BaseModel):
    """Raw row data as loaded from Excel file.
    
    Contains exact values from spreadsheet before any normalization.
    """
    # TODO: Add validation rules for raw data
    sku: str | None = Field(None, description="Product SKU from Excel")
    title: str | None = Field(None, description="Product title")
    price: Any | None = Field(None, description="Raw price value")
    discount_price: Any | None = Field(None, description="Raw discount price value")
    stock_qty: Any | None = Field(None, description="Raw stock quantity")
    currency: str | None = Field(None, description="Currency code")
    base_attributes: dict[str, Any] = Field(default_factory=dict, description="Other raw attributes")
    
    # Source tracking
    source_file: str = Field(..., description="Path to source Excel file")
    source_sheet: str = Field(..., description="Sheet name in Excel")
    source_row_index: int = Field(..., description="Zero-based row index")


class ExcelRowNormalized(BaseModel):
    """Normalized row data ready for merge operations.
    
    All fields are cleaned and typed according to domain requirements.
    """
    # TODO: Add computed fields for validation status
    sku: str = Field(..., description="Normalized SKU")
    title: str | None = Field(None, description="Normalized title")
    price: float | None = Field(None, ge=0, description="Normalized price")
    discount_price: float | None = Field(None, ge=0, description="Normalized discount price")
    stock_qty: int | None = Field(None, ge=0, description="Normalized stock quantity")
    currency: str = Field("RUB", description="Normalized currency code")
    base_attributes: dict[str, Any] = Field(default_factory=dict, description="Normalized attributes")
    
    # Source tracking preserved
    source_file: str = Field(..., description="Path to source Excel file")
    source_sheet: str = Field(..., description="Sheet name in Excel")
    source_row_index: int = Field(..., description="Zero-based row index")
    
    # Normalization metadata
    normalization_errors: list[str] = Field(default_factory=list, description="Issues during normalization")


# Helper type for flexible attribute handling
RawAttributes = dict[str, Any]
"""Type alias for raw attribute dictionary from Excel cells."""