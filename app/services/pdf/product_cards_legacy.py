"""
Product card extractor for PDF catalog pages.

Handles pages with individual product cards containing:
- SKU (e.g., G404, G1052-80)
- Product description
- Color/variant SKUs (e.g., G404-1, G404-5)
- Technical specifications

Each product card becomes a ProductBlock with multiple rows for variants.
"""

from __future__ import annotations
from pathlib import Path
from .extractor import ProductBlock, extract_text_from_page
from .normalizer import normalize_text


from .series_title import extract_series_title
from .nearby_page_title import _extract_nearby_page_title
from .title_candidates import _extract_title_candidates
from .variant_extractor import _extract_variants_from_block


from .card_boundaries import _find_product_card_boundaries
from .debug_helpers import _debug_card_extraction
from typing import Any, Optional
from .title_filters import _is_bad_title_candidate


from .product_card_quality import _is_meaningful_product_card


def extract_product_cards_from_page(
    pdf_path: str | Path,
    page_number: int,
    brand_hint: Optional[str] = None,
    source_file: Optional[str] = None,
) -> list[ProductBlock]:
    text = extract_text_from_page(pdf_path, page_number)
    if not text:
        return []

    text = normalize_text(text)
    if not text:
        return []

    page_title = extract_series_title(text) or ""

    boundaries = _find_product_card_boundaries(text)
    if not boundaries:
        return []

    blocks: list[ProductBlock] = []

    for start_pos, end_pos, main_sku in boundaries:
        block_text = text[start_pos:end_pos].strip()
        if not block_text:
            continue

        if not _is_meaningful_product_card(block_text, main_sku):
            continue

        variants = _extract_variants_from_block(block_text, main_sku)

        title_candidates = _extract_title_candidates(
            block_text=block_text,
            main_sku=main_sku,
            page_title=page_title,
        )

        nearby_title = _extract_nearby_page_title(
            full_text=text,
            start_pos=start_pos,
            main_sku=main_sku,
        )
        if nearby_title:
            title_candidates.append(nearby_title)

        chosen_title = None
        for candidate in title_candidates:
            if not _is_bad_title_candidate(candidate, main_sku):
                chosen_title = candidate
                break

        if not chosen_title:
            chosen_title = main_sku

        try:
            _debug_card_extraction(
                page_number=page_number,
                start_pos=start_pos,
                end_pos=end_pos,
                main_sku=main_sku,
                block_text=block_text,
                variants=variants,
                title_candidates=title_candidates,
                chosen_title=chosen_title,
            )
        except Exception:
            pass

        rows: list[dict[str, Any]] = [{"sku": sku} for sku in variants]

        blocks.append(
            ProductBlock(
                title=chosen_title,
                rows=rows,
                metadata={
                    "page_number": page_number,
                    "brand_hint": brand_hint,
                    "source_file": source_file,
                    "main_sku": main_sku,
                },
            )
        )

    return blocks
