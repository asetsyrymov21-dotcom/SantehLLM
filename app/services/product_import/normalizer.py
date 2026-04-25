"""
Normalization utilities for product import.

Handles text cleaning, identity key generation, and payload building.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Optional

from app.utils.sku_utils import normalize_sku as central_normalize_sku

logger = logging.getLogger(__name__)


def normalize_text(text: str | None) -> str:
    """Normalize text: trim, collapse whitespace."""
    if not text:
        return ""
    text = str(text).strip()
    text = re.sub(r"\s+", " ", text)
    return text


def normalize_text_for_comparison(text: str | None) -> str:
    """
    Normalize text for identity comparison.

    More aggressive than normalize_text - removes case and special chars.
    """
    if not text:
        return ""
    text = str(text).strip().lower()
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"[^\w\s]", "", text)
    return text


def normalize_sku(sku: str | None) -> Optional[str]:
    """Normalize SKU: delegate to central utility.

    This function is kept for backward compatibility.
    Use app.utils.sku_utils.normalize_sku directly for new code.
    """
    return central_normalize_sku(sku)


def product_identity_key(item: dict[str, Any]) -> tuple[str, ...]:
    """
    Generate stable identity key for deduplication.

    Priority:
    1. ('sku', normalized_sku) - most reliable
    2. ('fallback', normalized_name, brand, size) - for items without SKU

    Args:
        item: Raw product dict with sku, name, brand, attributes

    Returns:
        Tuple that uniquely identifies this product
    """
    # Try SKU first
    sku = central_normalize_sku(item.get("sku"))
    if sku:
        return ("sku", sku)

    # Fallback: name + brand + size from attributes
    name = normalize_text_for_comparison(item.get("name"))
    brand = normalize_text_for_comparison(item.get("brand"))

    # Try to get size from attributes
    size = ""
    attrs = item.get("attributes") or {}
    if isinstance(attrs, dict):
        size = normalize_text_for_comparison(
            attrs.get("size") or attrs.get("размер") or attrs.get("диаметр")
        )

    return ("fallback", name, brand, size)


def build_product_payload(raw_item: dict[str, Any]) -> dict[str, Any]:
    """
    Build final product payload from raw extracted item.

    Performs final normalization before database write.

    Args:
        raw_item: Dict with sku, name, brand, category, description,
                  attributes, source_file, source_page

    Returns:
        Dict compatible with ProductCreate schema
    """
    # Normalize basic fields
    sku = central_normalize_sku(raw_item.get("sku"))
    name = normalize_text(raw_item.get("name"))
    brand = normalize_text(raw_item.get("brand")) or None
    category = normalize_text(raw_item.get("category")) or None
    description = normalize_text(raw_item.get("description")) or None

    # Build attributes dict
    attrs = {}
    raw_attrs = raw_item.get("attributes") or {}

    if isinstance(raw_attrs, dict):
        for key, value in raw_attrs.items():
            if value is not None:
                clean_val = normalize_text(value) if isinstance(value, str) else value
                if clean_val:
                    attrs[key] = clean_val

    # Add source tracking to attributes
    if raw_item.get("source_file"):
        attrs["source_file"] = str(raw_item["source_file"])
    if raw_item.get("source_page"):
        attrs["source_page"] = raw_item["source_page"]

    return {
        "sku": sku,
        "name": name,
        "brand": brand,
        "category": category,
        "description": description,
        "attributes_json": attrs if attrs else None,
        "is_active": True,
    }
