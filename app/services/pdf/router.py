"""Router for PDF page extraction.

Provides unified interface for extracting products from any PDF page
by detecting page type and dispatching to appropriate extractor.

This module implements conservative routing:
- If page type is uncertain, uses legacy_default extractor
- No LLM fallback yet
- Local type logic stays isolated
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

from .extractor import extract_catalog_grids_from_page, extract_text_from_page
from .classifier import detect_page_type
from .page_types import PageType, normalize_page_type, is_product_cards_type
from .page_features import extract_page_features


if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


def _route_product_cards(
    pdf_path: str | Path,
    page_number: int,
    brand_hint: Optional[str],
    source_file: Optional[str],
    page_type: PageType,
) -> list[Any]:
    """Route product card pages to appropriate type-specific extractor.

    Conservative approach: delegates to legacy extractor initially.
    Type-specific extractors will be implemented incrementally.
    """
    from .product_cards_legacy import extract_product_cards_from_page

    # For now, all product card types use legacy extractor
    # Future: route to type-specific extractors based on page_type
    logger.info(
        "Page %s: routing product_cards (type=%s) to legacy extractor",
        page_number,
        page_type.value,
    )
    return extract_product_cards_from_page(
        pdf_path=pdf_path,
        page_number=page_number,
        brand_hint=brand_hint,
        source_file=source_file,
    )


def extract_page_products(
    pdf_path: str | Path,
    page_number: int,
    brand_hint: Optional[str] = None,
    source_file: Optional[str] = None,
) -> list[Any]:
    """Extract products from a PDF page with automatic type detection.

    This is the main entry point for page extraction. It:
    1. Detects the page type (grid_catalog, product_cards, marketing, unknown)
    2. Routes to appropriate extractor
    3. Returns list of ProductBlock objects

    Conservative routing:
    - If type detection is uncertain, falls back to legacy_default
    - No LLM fallback (not implemented yet)
    - Preserves all existing extraction behavior

    Args:
        pdf_path: Path to PDF file
        page_number: 1-based page number
        brand_hint: Brand name if known from filename/context
        source_file: Original filename for tracking

    Returns:
        List of ProductBlock objects (may be empty)
    """
    logger.info("Extracting products from %s page %s", pdf_path, page_number)

    # Get page text and detect features
    text = extract_text_from_page(pdf_path, page_number)

    # Detect page type using legacy classifier
    legacy_type_str = detect_page_type(text, page_number=page_number)
    page_type = normalize_page_type(legacy_type_str)

    # Extract features for potential routing decisions
    features = extract_page_features(text, page_number=page_number)

    logger.info(
        "Page %s detected as: %s (normalized: %s)",
        page_number,
        legacy_type_str,
        page_type.value,
    )

    # Route to appropriate extractor
    if page_type == PageType.GRID_CATALOG:
        return extract_catalog_grids_from_page(
            pdf_path, page_number, brand_hint, source_file
        )

    elif is_product_cards_type(page_type):
        return _route_product_cards(
            pdf_path, page_number, brand_hint, source_file, page_type
        )

    elif page_type == PageType.MARKETING:
        logger.debug("Page %s is marketing, returning empty list", page_number)
        return []

    elif page_type == PageType.CATEGORY_INDEX:
        logger.debug("Page %s is category index, returning empty list", page_number)
        return []

    else:  # unknown or legacy_default
        logger.warning(
            "Page %s type uncertain (%s), returning empty list",
            page_number,
            page_type.value,
        )
        return []


def extract_multiple_pages(
    pdf_path: str | Path,
    page_numbers: list[int],
    brand_hint: Optional[str] = None,
    source_file: Optional[str] = None,
    skip_empty: bool = True,
) -> dict[int, list[Any]]:
    """Extract products from multiple pages.

    Args:
        pdf_path: Path to PDF file
        page_numbers: List of 1-based page numbers
        brand_hint: Brand name if known
        source_file: Original filename for tracking
        skip_empty: If True, exclude pages with no products from result

    Returns:
        Dictionary mapping page_number -> list of ProductBlock
    """
    results = {}

    for page_num in page_numbers:
        try:
            blocks = extract_page_products(pdf_path, page_num, brand_hint, source_file)

            if blocks or not skip_empty:
                results[page_num] = blocks

        except Exception as e:
            logger.error("Failed to extract page %s: %s", page_num, e)
            if not skip_empty:
                results[page_num] = []

    return results


def inspect_page(
    pdf_path: str | Path,
    page_number: int,
) -> dict[str, Any]:
    """Inspect a PDF page and return diagnostic information.

    Useful for debugging and understanding page structure.

    Args:
        pdf_path: Path to PDF file
        page_number: 1-based page number

    Returns:
        Dictionary with page analysis:
            - page_number: page number
            - page_type: detected type
            - text_sample: first 500 chars of text
            - text_length: total text length
            - line_count: number of non-empty lines
            - sku_count: estimated SKU count
    """
    from .classifier import is_valid_sku

    text = extract_text_from_page(pdf_path, page_number)

    # Get legacy type
    legacy_type_str = detect_page_type(text, page_number=page_number)
    page_type = normalize_page_type(legacy_type_str)

    # Get features
    features = extract_page_features(text, page_number=page_number)

    lines = [l for l in text.split("n") if l.strip()]

    # Count potential SKUs
    import re

    sku_pattern = re.compile(r"b[A-Z]\d{3,}(?:-\d{1,3}[A-Z]?)?\b", re.IGNORECASE)
    sku_matches = sku_pattern.findall(text)

    return {
        "page_number": page_number,
        "page_type": page_type.value,
        "legacy_type": legacy_type_str,
        "text_sample": text[:500] + "..." if len(text) > 500 else text,
        "text_length": features.text_length,
        "line_count": features.line_count,
        "sku_count": len(features.distinct_skus),
        "has_card_structure": features.has_card_structure,
        "has_repeated_blocks": features.has_repeated_blocks,
    }
