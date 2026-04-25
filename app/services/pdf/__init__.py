"""
PDF extraction services for catalog processing.

This module provides page-by-page PDF extraction for large catalog files
to avoid memory issues with 120-300 MB PDFs.
"""

from .inspector import inspect_pdf, PdfInfo
from .extractor import (
    extract_text_from_page,
    extract_table_from_page,
    extract_product_block_from_page,
    extract_catalog_grids_from_page,
    ProductBlock,
)
from .classifier import detect_page_type, is_valid_sku
from .product_cards import extract_product_cards_from_page
from .router import extract_page_products, extract_multiple_pages, inspect_page
from .normalizer import normalize_sku, normalize_text, clean_cell_value
from .mapper import map_product_block_to_create, map_table_row_to_product

__all__ = [
    # Inspector
    "inspect_pdf",
    "PdfInfo",
    # Core extractors
    "extract_text_from_page",
    "extract_table_from_page",
    "extract_product_block_from_page",
    "extract_catalog_grids_from_page",
    "ProductBlock",
    # Classification
    "detect_page_type",
    "is_valid_sku",
    # Product cards
    "extract_product_cards_from_page",
    # Router
    "extract_page_products",
    "extract_multiple_pages",
    "inspect_page",
    # Normalization
    "normalize_sku",
    "normalize_text",
    "clean_cell_value",
    # Mapping
    "map_product_block_to_create",
    "map_table_row_to_product",
]
