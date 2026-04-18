"\"\"\"Extractor for multi-column product card layouts.

Handles pages where products are presented in multiple columns (2-col, 3-col, etc.)
Initially delegates to legacy extractor.
\"\"\"

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

from .extraction_types import ExtractionResult, PageFeatures
from .product_cards_legacy import extract_product_cards_legacy

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


def extract_columns_layout(
    pdf_path: str | Path,
    page_number: int,
    brand_hint: Optional[str] = None,
    source_file: Optional[str] = None,
    features: Optional[PageFeatures] = None,
) -> ExtractionResult:
    \"\"\"Extract product cards from multi-column layout pages.

    Args:
        pdf_path: Path to PDF file
        page_number: 1-based page number
        brand_hint: Brand name if known from filename/context
        source_file: Original filename for tracking
        features: Optional pre-computed page features

    Returns:
        List of ProductBlock objects
    \"\"\"
    logger.info(
        "[COLUMNS_LAYOUT] Page %s: delegating to legacy extractor", page_number
    )
    
    # Currently delegates to legacy extractor
    # Future: implement multi-column specific extraction logic
    return extract_product_cards_legacy(
        pdf_path=pdf_path,
        page_number=page_number,
        brand_hint=brand_hint,
        source_file=source_file,
    )"