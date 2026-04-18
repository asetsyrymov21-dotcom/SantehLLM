from __future__ import annotations

from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class ExtractedProduct(BaseModel):
    sku: Optional[str] = None
    name: Optional[str] = None
    price: Optional[float] = None
    brand: Optional[str] = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class ExtractionAuditRecord(BaseModel):
    page: int
    page_type: str
    products_found: int = 0
    products: List[ExtractedProduct] = Field(default_factory=list)
    status: str = "success"
    error: Optional[str] = None
    source_file: Optional[str] = None
    has_sku: bool = False
    has_name: bool = False
    skip_reason: Optional[str] = None


class ExtractionAuditSummary(BaseModel):
    total_pages_tested: int = 0
    pages_by_type: Dict[str, int] = Field(default_factory=dict)
    successful_pages: int = 0
    error_pages: int = 0
    empty_pages: int = 0
    skipped_pages: int = 0
    total_products_extracted: int = 0
    pages_without_sku: int = 0
    pages_without_name: int = 0
    errors_by_type: Dict[str, int] = Field(default_factory=dict)
