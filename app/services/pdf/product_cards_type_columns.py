"""Extractor for multi-column product card layouts."""

from __future__ import annotations

import logging
from pathlib import Path

from .extraction_types import ExtractionResult, PageFeatures
from .product_cards_legacy import extract_product_cards_from_page

logger = logging.getLogger(__name__)


def extract_columns_layout(
    pdf_path: str | Path,
    page_number: int,
    brand_hint: str | None = None,
    source_file: str | None = None,
    features: PageFeatures | None = None,
) -> ExtractionResult:
    logger.info(
        "[COLUMNS_LAYOUT] Page %s: delegating to legacy extractor", page_number
    )
    return extract_product_cards_from_page(
        pdf_path=pdf_path,
        page_number=page_number,
        brand_hint=brand_hint,
        source_file=source_file,
    )
