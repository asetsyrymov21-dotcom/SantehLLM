"""Schemas for product merging and unification.

Defines Pydantic models for merged product representation with provenance.
"""

from datetime import datetime
from typing import Any
from pydantic import BaseModel, Field


class FieldProvenance(BaseModel):
    """Provenance metadata for a single field value."""
    source: str = Field(..., description="Source type: excel, pdf, llm, manual")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Confidence score")
    extracted_at: datetime = Field(default_factory=datetime.utcnow, description="Extraction timestamp")
    raw_value: Any | None = Field(None, description="Original raw value before normalization")
    notes: str | None = Field(None, description="Additional notes about extraction")


class MergeDecision(BaseModel):
    """Record of a merge decision for audit purposes."""
    field_name: str = Field(..., description="Field that was merged")
    selected_source: str = Field(..., description="Source that won")
    rejected_sources: list[str] = Field(default_factory=list, description="Sources not selected")
    reason: str | None = Field(None, description="Why this decision was made")
    confidence_delta: float | None = Field(None, description="Confidence difference between top candidates")


class ProductUnified(BaseModel):
    """Fully merged product representation with full provenance.
    
    This is the canonical product format combining all sources.
    """
    # Identity
    product_id: str | None = Field(None, description="Internal product ID if exists")
    sku: str = Field(..., description="Product SKU")
    
    # Core product info
    title: str | None = Field(None, description="Product title")
    brand: str | None = Field(None, description="Brand name")
    category: str | None = Field(None, description="Category path")
    description: str | None = Field(None, description="Full description")
    
    # Attributes
    base_attributes: dict[str, Any] = Field(default_factory=dict, description="Core attributes from Excel")
    extended_attributes: dict[str, Any] = Field(default_factory=dict, description="Enriched attributes from PDF/LLM")
    
    # Commercial data
    price: float | None = Field(None, ge=0, description="Current price")
    discount_price: float | None = Field(None, ge=0, description="Discounted price if applicable")
    stock_qty: int | None = Field(None, ge=0, description="Available quantity")
    stock_status: str = Field("unknown", description="Stock status: in_stock, out_of_stock, preorder, unknown")
    currency: str = Field("RUB", description="Currency code")
    
    # Media
    pdf_pages: list[int] = Field(default_factory=list, description="Page numbers where product appears in PDF")
    images: list[str] = Field(default_factory=list, description="Image URLs or paths")
    
    # Source references
    source_refs: dict[str, Any] = Field(default_factory=dict, description="Reference to all source files")
    
    # Merge metadata
    merge_status: str = Field("pending", description="Status: pending, merged, conflict, failed")
    confidence: float = Field(0.0, ge=0.0, le=1.0, description="Overall merge confidence")
    
    # Provenance tracking (per field)
    field_provenance: dict[str, FieldProvenance] = Field(default_factory=dict, description="Source info for each field")
    merge_decisions: list[MergeDecision] = Field(default_factory=list, description="Log of merge decisions made")
    
    # Timestamps
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)