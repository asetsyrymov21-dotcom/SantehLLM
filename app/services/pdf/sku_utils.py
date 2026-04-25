from __future__ import annotations

import re


def looks_like_main_product_sku(sku: str) -> bool:
    """Strict check for SKU that can start a real product card."""
    sku = sku.strip().upper()

    # Base product like G1006 or G404
    if re.fullmatch(r"[A-Z]\d{3,}", sku):
        return True

    # Standalone product like G1006-33, G1206-233
    if re.fullmatch(r"[A-Z]\d{3,}-\d{1,3}[A-Z]?", sku):
        return True

    return False
