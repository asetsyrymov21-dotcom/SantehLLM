from __future__ import annotations
import re
from .variant_extractor import _extract_variants_from_block


def _clean_product_description(text: str) -> str:
    """Clean and extract product description from card text."""
    cleaned = re.sub(r"\s+", " ", text).strip()

    # Remove leading series / brand fragments only at the start
    cleaned = re.sub(r"^(GAPPO|FRAP)\s+", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(
        r"^[A-Z]\d+[A-Z0-9-]*\s+Серия\s+[^A-Z\d]{0,80}",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )

    # Remove the first main SKU token from the start of the block
    cleaned = re.sub(
        r"^[A-Z]\d{3,}(?:-\d{1,3}[A-Z]?)?\b\s*",
        "",
        cleaned,
        flags=re.IGNORECASE,
    )

    # Remove obvious tech/noise fragments, but do NOT drop the whole text
    cleaned = re.sub(r"\b\d+\s*[/x]\s*\d+\s*PCS\b", " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\b\d+\s*mm\b", " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\b\d+\s*ml\b", " ", cleaned, flags=re.IGNORECASE)

    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    if len(cleaned) > 200:
        cleaned = cleaned[:197] + "..."

    return cleaned


def _is_meaningful_product_card(block_text: str, main_sku: str) -> bool:
    """Check if extracted block represents a valid product card."""
    # Must have the main SKU
    if main_sku not in block_text.upper():
        return False

    # Must have some descriptive content
    cleaned = _clean_product_description(block_text)
    if len(cleaned) < 5:
        # Check for variant SKUs as fallback
        variants = _extract_variants_from_block(block_text, main_sku)
        return len(variants) > 1

    return True
