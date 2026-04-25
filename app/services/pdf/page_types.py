"""Page type definitions and enums for PDF extraction.

This module defines the canonical page types used across the PDF pipeline.
Type detection is conservative - uncertain pages should route to legacy_default.
"""

from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass


class PageType(str, Enum):
    """Canonical page types for PDF catalog pages."""

    # Grid layout with series headers and dense SKU lists
    GRID_CATALOG = "grid_catalog"

    # Product cards in single/linear layout
    PRODUCT_CARDS_SINGLE = "product_cards_single"

    # Product cards in multi-column layout
    PRODUCT_CARDS_COLUMNS = "product_cards_columns"

    # Product cards in grid layout (2x2, 3x3, etc.)
    PRODUCT_CARDS_GRID = "product_cards_grid"

    # Generic product cards (unknown sub-type)
    PRODUCT_CARDS = "product_cards"

    # Category index/overview page
    CATEGORY_INDEX = "category_index"

    # Marketing/image-heavy page
    MARKETING = "marketing"

    # Unknown/unclassified
    UNKNOWN = "unknown"

    # Conservative fallback for uncertain detection
    LEGACY_DEFAULT = "legacy_default"


# Legacy type mappings for backward compatibility
LEGACY_TYPE_MAP: dict[str, PageType] = {
    "grid_catalog": PageType.GRID_CATALOG,
    "product_cards": PageType.PRODUCT_CARDS,
    "category_index": PageType.CATEGORY_INDEX,
    "marketing": PageType.MARKETING,
    "unknown": PageType.UNKNOWN,
}


def normalize_page_type(legacy_type: str) -> PageType:
    """Convert legacy string type to canonical PageType enum."""
    return LEGACY_TYPE_MAP.get(legacy_type, PageType.LEGACY_DEFAULT)


def is_product_cards_type(page_type: PageType) -> bool:
    """Check if page type is any variant of product cards."""
    return page_type in {
        PageType.PRODUCT_CARDS,
        PageType.PRODUCT_CARDS_SINGLE,
        PageType.PRODUCT_CARDS_COLUMNS,
        PageType.PRODUCT_CARDS_GRID,
    }
