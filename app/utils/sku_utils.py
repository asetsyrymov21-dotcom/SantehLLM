"""Centralized SKU utilities for Santeh Catalog.

All SKU normalization and brand derivation should go through this module.
"""

from __future__ import annotations

import re
from typing import Optional


def normalize_sku(sku: Optional[str]) -> Optional[str]:
    """Normalize SKU for consistent matching across the system.

    Steps:
        - Strip whitespace
        - Convert to uppercase
        - Collapse multiple spaces
        - Normalize dashes (em-dash, en-dash -> hyphen)
        - Remove common prefixes (арт., артикул, код, etc.)

    Args:
        sku: Raw SKU string or None

    Returns:
        Normalized SKU string or None if empty/invalid

    Examples:
        >>> normalize_sku("  f1002-b  ")
        'F1002-B'
        >>> normalize_sku("арт. G1234")
        'G1234'
        >>> normalize_sku("f1002–b")  # em-dash
        'F1002-B'
        >>> normalize_sku("  ")
        None
    """
    if not sku:
        return None

    # Convert to string and strip
    sku = str(sku).strip()
    if not sku:
        return None

    # Convert to uppercase
    sku = sku.upper()

    # Normalize various dash types to hyphen
    # em-dash (—), en-dash (–), minus sign (−), non-breaking hyphen
    sku = sku.replace("—", "-").replace("–", "-").replace("−", "-").replace("‑", "-")

    # Collapse multiple spaces to single
    sku = re.sub(r"\s+", " ", sku)

    # Remove common prefixes (case insensitive)
    prefixes = [
        "АРТ.",
        "АРТИКУЛ",
        "КОД",
        "CODE",
        "МОДЕЛЬ",
        "MODEL",
        "№",
        "NR.",
        "ART.",
        "ARTICLE",
    ]
    for prefix in prefixes:
        sku = re.sub(rf"^{prefix}[:\s]*", "", sku, flags=re.IGNORECASE)

    # Final cleanup: remove any remaining invalid characters except alphanumeric, hyphen, dot
    # But preserve structure like F1002-B or G1234.5
    sku = re.sub(r"[^\w\-\.]", "", sku)

    # Remove leading/trailing hyphens
    sku = sku.strip("-")

    return sku if sku else None


def derive_brand_from_sku(sku: Optional[str]) -> Optional[str]:
    """Derive brand from SKU prefix.

    Rules:
        - SKU starting with "F" -> "FRAP"
        - SKU starting with "G" -> "GAPPO"
        - Otherwise -> None

    Args:
        sku: SKU string (will be normalized if needed)

    Returns:
        Brand name or None

    Examples:
        >>> derive_brand_from_sku("F1002-B")
        'FRAP'
        >>> derive_brand_from_sku("G1234")
        'GAPPO'
        >>> derive_brand_from_sku("XYZ123")
        None
    """
    if not sku:
        return None

    # Normalize first to ensure consistent matching
    normalized = normalize_sku(sku)
    if not normalized:
        return None

    # Check first character after normalization
    first_char = normalized[0].upper()

    if first_char == "F":
        return "FRAP"
    elif first_char == "G":
        return "GAPPO"
    else:
        return None


def is_frap_sku(sku: Optional[str]) -> bool:
    """Check if SKU belongs to FRAP brand."""
    brand = derive_brand_from_sku(sku)
    return brand == "FRAP"


def is_gappo_sku(sku: Optional[str]) -> bool:
    """Check if SKU belongs to GAPPO brand."""
    brand = derive_brand_from_sku(sku)
    return brand == "GAPPO"


def get_brand_from_normalized_sku(normalized_sku: str) -> Optional[str]:
    """Fast brand lookup for already normalized SKU.

    Use this when SKU is already normalized to avoid double work.

    Args:
        normalized_sku: Already normalized SKU string

    Returns:
        Brand name or None
    """
    if not normalized_sku:
        return None

    first_char = normalized_sku[0].upper()

    if first_char == "F":
        return "FRAP"
    elif first_char == "G":
        return "GAPPO"
    else:
        return None
