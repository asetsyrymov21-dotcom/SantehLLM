from __future__ import annotations
import re
from .classifier import is_valid_sku
from .shared_patterns import MAIN_SKU_PATTERN


def _extract_variants_from_block(block_text: str, main_sku: str) -> list[str]:
    """
    Extract SKU variants that belong to the current main SKU block.
    """
    variants: list[str] = []
    seen: set[str] = set()

    all_skus = [m.group(1).upper() for m in MAIN_SKU_PATTERN.finditer(block_text)]

    if main_sku not in seen:
        variants.append(main_sku)
        seen.add(main_sku)

    if "-" in main_sku:
        base_prefix = main_sku.split("-", 1)[0]
    else:
        base_prefix = main_sku

    for sku in all_skus:
        if not is_valid_sku(sku):
            continue

        if sku in seen:
            continue

        # same exact sku
        if sku == main_sku:
            continue

        # variants of base item, like G404-1 / G404-5 for G404
        if sku.startswith(base_prefix + "-"):
            variants.append(sku)
            seen.add(sku)
            continue

        # for products like G1052-80, allow closely related variants
        if "-" in main_sku and sku.startswith(base_prefix + "-"):
            variants.append(sku)
            seen.add(sku)
            continue

    return variants
