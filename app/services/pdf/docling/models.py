"""
Pydantic models for Docling extraction results.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, Field


class PageType(str, Enum):
    """Classification of page content type."""
    TABLE = "table"           # Structured table with SKUs
    GALLERY = "gallery"       # Images with SKUs below
    TEXT = "text"             # Text only, no products
    MIXED = "mixed"           # Combination
    EMPTY = "empty"           # No content


class TableRow(BaseModel):
    """Single row from product table."""
    sku: Optional[str] = None
    cells: dict[str, Any] = Field(default_factory=dict)
    raw_text: str = ""
    
    class Config:
        extra = "allow"


class ImageItem(BaseModel):
    """Image with associated text/SKU from gallery page."""
    image_index: int
    caption: str = ""           # Text below or near image
    sku: Optional[str] = None   # Extracted SKU from caption
    surrounding_text: str = ""  # Context around image
    bbox: Optional[tuple] = None  # Bounding box if needed


class ExtractionResult(BaseModel):
    """
    Result of extracting a single PDF page.
    
    Universal container that works for both table and gallery pages.
    """
    page_number: int
    page_type: PageType
    
    # Common metadata
    title: Optional[str] = None
    subtitle: Optional[str] = None
    brand_hint: Optional[str] = None
    
    # Table-specific
    table_headers: list[str] = Field(default_factory=list)
    table_rows: list[TableRow] = Field(default_factory=list)
    
    # Gallery-specific
    image_items: list[ImageItem] = Field(default_factory=list)
    
    # Raw for debugging
    raw_text: str = ""
    docling_items: list[str] = Field(default_factory=list)  # Item types found
    
    # Source tracking
    source_file: Optional[str] = None
    processing_time_ms: Optional[float] = None
    
    def has_products(self) -> bool:
        """Check if any products were found."""
        if self.page_type == PageType.TABLE:
            return len(self.table_rows) > 0
        elif self.page_type == PageType.GALLERY:
            return len(self.image_items) > 0
        return False
    
    def to_simple_dict(self) -> dict:
        """Simplified dict for JSON export."""
        return {
            "page_number": self.page_number,
            "page_type": self.page_type.value,
            "title": self.title,
            "has_products": self.has_products(),
            "product_count": len(self.table_rows) if self.table_type else len(self.image_items),
            "preview": self._get_preview(),
        }
    
    def _get_preview(self) -> str:
        """Short preview of found products."""
        if self.page_type == PageType.TABLE and self.table_rows:
            skus = [r.sku for r in self.table_rows[:3] if r.sku]
            return f"SKUs: {', '.join(skus)}..." if skus else "Table found"
        elif self.page_type == PageType.GALLERY and self.image_items:
            skus = [i.sku for i in self.image_items[:3] if i.sku]
            return f"Images with SKUs: {', '.join(skus)}..." if skus else f"{len(self.image_items)} images"
        return "No products"
