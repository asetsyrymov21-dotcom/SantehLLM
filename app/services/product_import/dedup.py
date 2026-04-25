"""
Deduplication logic for product import.

Handles both local (within single import batch) and database-level deduplication.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from .normalizer import product_identity_key, normalize_text

logger = logging.getLogger(__name__)


@dataclass
class ProductIdentity:
    """Represents a deduplicated product with merged data."""
    
    identity_key: tuple[str, ...]
    sku: str | None
    name: str
    brand: str | None
    category: str | None
    description: str | None
    attributes: dict[str, Any] = field(default_factory=dict)
    sources: list[dict] = field(default_factory=list)  # Track all source records
    
    @property
    def is_sku_based(self) -> bool:
        """Check if identity is based on SKU (preferred) or fallback."""
        return self.identity_key[0] == 'sku'
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to import-ready dict."""
        result = {
            'sku': self.sku,
            'name': self.name,
            'brand': self.brand,
            'category': self.category,
            'description': self.description,
            'attributes': self.attributes.copy(),
        }
        
        # Add source tracking from first source
        if self.sources:
            first = self.sources[0]
            if first.get('source_file'):
                result['source_file'] = first['source_file']
            if first.get('source_page'):
                result['source_page'] = first['source_page']
        
        return result


def deduplicate_items_locally(items: list[dict[str, Any]]) -> list[ProductIdentity]:
    """
    Deduplicate items within import batch.
    
    If same SKU appears multiple times:
    - Merge attributes (union of all keys)
    - Keep longest/best description
    - Track all sources for audit
    
    Args:
        items: Raw extracted product dicts
        
    Returns:
        List of unique ProductIdentity objects
    """
    logger.info(f"Starting local deduplication of {len(items)} items")
    
    # Group by identity key
    groups: dict[tuple, list[dict]] = {}
    
    for item in items:
        key = product_identity_key(item)
        if key not in groups:
            groups[key] = []
        groups[key].append(item)
    
    logger.info(f"Found {len(groups)} unique identity groups")
    
    # Merge each group
    results: list[ProductIdentity] = []
    
    for key, group_items in groups.items():
        merged = _merge_product_group(key, group_items)
        if merged:
            results.append(merged)
    
    # Sort: SKU-based first (more reliable), then by name
    results.sort(key=lambda x: (not x.is_sku_based, x.name))
    
    logger.info(f"After deduplication: {len(results)} unique products")
    return results


def _merge_product_group(
    identity_key: tuple,
    items: list[dict[str, Any]]
) -> ProductIdentity | None:
    """
    Merge multiple items with same identity into single ProductIdentity.
    
    Strategy:
    - Use first non-empty value for simple fields
    - Merge attributes (union)
    - Keep longest description
    - Track all sources
    """
    if not items:
        return None
    
    # Initialize from first item
    first = items[0]
    
    sku = first.get('sku')
    name = str(first.get('name', '')).strip()
    brand = first.get('brand')
    category = first.get('category')
    description = first.get('description') or first.get('short_description')
    
    # Start with first item's attributes
    merged_attrs: dict[str, Any] = {}
    first_attrs = first.get('attributes') or {}
    if isinstance(first_attrs, dict):
        merged_attrs.update(first_attrs)
    
    # Track sources
    sources = [_extract_source_info(first)]
    
    # Merge remaining items
    for item in items[1:]:
        sources.append(_extract_source_info(item))
        
        # Prefer non-empty values
        if not sku:
            sku = item.get('sku')
        if not brand:
            brand = item.get('brand')
        if not category:
            category = item.get('category')
        
        # Keep longest description
        item_desc = item.get('description') or item.get('short_description')
        if item_desc:
            item_desc = str(item_desc).strip()
            if not description or len(item_desc) > len(description):
                description = item_desc
        
        # Merge attributes
        item_attrs = item.get('attributes') or {}
        if isinstance(item_attrs, dict):
            for key, value in item_attrs.items():
                if value is not None:
                    # If key exists, prefer non-empty or longer value
                    existing = merged_attrs.get(key)
                    if existing is None:
                        merged_attrs[key] = value
                    elif isinstance(existing, str) and isinstance(value, str):
                        if len(str(value)) > len(str(existing)):
                            merged_attrs[key] = value
    
    return ProductIdentity(
        identity_key=identity_key,
        sku=sku,
        name=name,
        brand=brand,
        category=category,
        description=description,
        attributes=merged_attrs,
        sources=sources,
    )


def _extract_source_info(item: dict[str, Any]) -> dict[str, Any]:
    """Extract source tracking info from item."""
    return {
        'source_file': item.get('source_file'),
        'source_page': item.get('source_page'),
        'sku': item.get('sku'),
        'name': item.get('name'),
    }


def find_conflicts(
    items: list[ProductIdentity],
    existing_skus: set[str]
) -> list[tuple[ProductIdentity, str]]:
    """
    Find potential conflicts between import batch and existing products.
    
    Returns:
        List of (identity, conflict_reason) tuples
    """
    conflicts = []
    
    for identity in items:
        if identity.sku and identity.sku in existing_skus:
            conflicts.append((identity, f"SKU '{identity.sku}' already exists in database"))
    
    return conflicts
