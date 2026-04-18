\"\"\"Common types and data structures for PDF extraction.

This module contains shared types used across all extractors.
\"\"\"

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional


@dataclass
class ExtractedRow:
    \"\"\"Single row in a product block (typically one SKU variant).\"\"\"    sku: str
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass
class ProductBlock:
    \"\"\"Container for extracted product data from a page section.

    Represents either:
    - A product family with multiple SKU variants (rows)
    - A single product with one SKU
    \"\"\"    title: str
    subtitle: str = \"\"
    brand: Optional[str] = None
    page_number: int = 0
    rows: list[dict[str, Any]] = field(default_factory=list)
    source_file: str = \"\"
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        \"\"\"Ensure rows are properly formatted.\"\"\"        if self.rows is None:
            self.rows = []


@dataclass
class PageFeatures:
    \"\"\"Features detected from a PDF page for routing decisions.\"\"\"    # Basic text metrics
    text: str = \"\"
    normalized_text: str = \"\"
    text_length: int = 0
    line_count: int = 0

    # SKU metrics
    sku_count: int = 0
    sku_density: float = 0.0  # SKUs per line
    distinct_skus: list[str] = field(default_factory=list)

    # Layout signals
    has_line_breaks: bool = False
    estimated_columns: int = 1

    # Content signals
    has_product_descriptors: bool = False
    has_grid_header: bool = False
    has_card_structure: bool = False
    has_repeated_blocks: bool = False

    # Page metadata
    page_number: int = 0
    source_file: Optional[str] = None

    def is_dense_sku_list(self, threshold: int = 5) -> bool:
        \"\"\"Check if page has dense SKU listing.\"\"\"        return self.sku_count >= threshold and self.sku_density > 0.3

    def has_meaningful_descriptors(self, min_count: int = 2) -> bool:
        \"\"\"Check if page has enough product descriptors.\"\"        # This is a placeholder - actual implementation in page_features
        return self.has_product_descriptors


# Type alias for extractor results
ExtractionResult = list[ProductBlock]


# Registry type for extractors
ExtractorRegistry = dict[str, Any]