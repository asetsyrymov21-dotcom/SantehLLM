"""Common types and data structures for PDF extraction."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ExtractedRow:
    """Single row in a product block, typically one SKU variant."""

    sku: str
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass
class ProductBlock:
    """Container for extracted product data from a page section."""

    title: str
    subtitle: str = ""
    brand: str | None = None
    page_number: int = 0
    rows: list[dict[str, Any]] = field(default_factory=list)
    source_file: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.rows is None:
            self.rows = []


@dataclass
class PageFeatures:
    """Features detected from a PDF page for routing decisions."""

    text: str = ""
    normalized_text: str = ""
    text_length: int = 0
    line_count: int = 0

    sku_count: int = 0
    sku_density: float = 0.0
    distinct_skus: list[str] = field(default_factory=list)

    has_line_breaks: bool = False
    estimated_columns: int = 1

    has_product_descriptors: bool = False
    has_grid_header: bool = False
    has_card_structure: bool = False
    has_repeated_blocks: bool = False

    page_number: int = 0
    source_file: str | None = None

    def is_dense_sku_list(self, threshold: int = 5) -> bool:
        return self.sku_count >= threshold and self.sku_density > 0.3

    def has_meaningful_descriptors(self, min_count: int = 2) -> bool:
        return self.has_product_descriptors


ExtractionResult = list[ProductBlock]
ExtractorRegistry = dict[str, Any]
