"""
Mapper module for converting PDF-extracted data to ProductCreate schemas.

Handles transformation from raw product blocks to database-ready structures.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

from app.schemas.product import ProductCreate
from .normalizer import normalize_text, normalize_sku, normalize_number

logger = logging.getLogger(__name__)


def map_product_block_to_create(
    block: Any,  # ProductBlock type
    default_category: str = "Сантехника",
) -> list[ProductCreate]:
    """
    Convert ProductBlock to list of ProductCreate objects.
    
    Each table row becomes a separate product with composite name.
    
    Args:
        block: ProductBlock with title, subtitle, and rows
        default_category: Fallback category if not detected
        
    Returns:
        List of ProductCreate ready for database import
    """
    from .extractor import ProductBlock
    
    if not isinstance(block, ProductBlock):
        raise TypeError(f"Expected ProductBlock, got {type(block)}")
    
    if not block.rows:
        logger.warning(f"No rows in block from page {block.page_number}")
        return []
    
    products = []
    
    for idx, row in enumerate(block.rows):
        try:
            product = map_table_row_to_product(
                row=row,
                title=block.title,
                subtitle=block.subtitle,
                brand=block.brand,
                category=default_category,
                source_file=block.source_file,
                source_page=block.page_number,
                row_index=idx,
            )
            if product:
                products.append(product)
        except Exception as e:
            logger.error(f"Error mapping row {idx}: {e}")
            continue
    
    logger.info(f"Mapped {len(products)} products from block")
    return products


def map_table_row_to_product(
    row: dict[str, Any],
    title: str,
    subtitle: str,
    brand: Optional[str],
    category: str,
    source_file: Optional[str],
    source_page: int,
    row_index: int = 0,
) -> Optional[ProductCreate]:
    """
    Convert single table row to ProductCreate.
    
    Args:
        row: Table row dict with normalized fields
        title: Product title from page
        subtitle: Product subtitle/description
        brand: Brand name
        category: Product category
        source_file: Original PDF filename
        source_page: Page number in PDF
        row_index: Row index for debugging
        
    Returns:
        ProductCreate or None if invalid
    """
    # Get SKU
    sku = normalize_sku(row.get('sku') or row.get('артикул'))
    if not sku:
        logger.warning(f"Row {row_index}: no SKU found")
        return None
    
    # Build product name: "{title} {size}"
    size = row.get('size', '')
    if size:
        name = f"{title} {size}"
    else:
        name = title
    
    name = normalize_text(name, max_length=255)
    
    # Build attributes dict
    attributes = {
        k: v for k, v in {
            "size": row.get('size'),
            "nominal_pressure": row.get('nominal_pressure'),
            "working_pressure_bar": row.get('working_pressure_bar'),
            "working_temperature_c": row.get('working_temperature_c'),
            "package_m": row.get('package_m'),
            "source_file": source_file,
            "source_page": source_page,
            "source_row": row_index,
        }.items() if v is not None
    }
    
    # Add any other fields from row
    for key, value in row.items():
        if key not in attributes and key not in ['sku', 'артикул']:
            attributes[key] = value
    
    return ProductCreate(
        sku=sku,
        name=name,
        brand=brand,
        category=category,
        description=normalize_text(subtitle),
        attributes_json=attributes if attributes else None,
        is_active=True,
    )


def detect_category_from_title(title: str) -> str:
    """
    Detect product category from title heuristics.
    
    Args:
        title: Product title
        
    Returns:
        Category name
    """
    title_lower = title.lower()
    
    # Category mappings
    categories = {
        "труб": "Трубы",
        "труба": "Трубы",
        "фитинг": "Фитинги",
        "смеситель": "Смесители",
        "кран": "Краны",
        "вентиль": "Вентили",
        "клапан": "Клапаны",
        "унитаз": "Унитазы",
        "раковин": "Раковины",
        "ванн": "Ванны",
        "душ": "Душевые системы",
        "коллектор": "Коллекторы",
        "насос": "Насосы",
        "радиатор": "Радиаторы",
        "полотенцесушитель": "Полотенцесушители",
    }
    
    for keyword, category in categories.items():
        if keyword in title_lower:
            return category
    
    return "Сантехника"
