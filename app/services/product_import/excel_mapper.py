"""Excel column mapping and schema conversion.

Maps raw Excel columns to standardized field names.
"""

import re
from typing import Any


# Aliases for matching Russian headers from price lists
DEFAULT_COLUMN_ALIASES: dict[str, list[str]] = {
    "sku": ["sku", "артикул", "арт.", "код", "code", "id"],
    "title": [
        "title",
        "название",
        "наименование",
        "наименавание",
        "имя",
        "name",
        "продукт",
        "модель",
        "model",
    ],
    "price": ["price", "цена", "стоимость", "розница", "ррц", "ррц ( тенге)"],
    "discount_price": [
        "discount_price",
        "цена со скидкой",
        "цена со скидкой(тенге)",
        "акция",
        "sale_price",
    ],
}


def normalize_header_name(header: str) -> str:
    """Normalize column header for matching.

    Trims whitespace, converts to lowercase, collapses multiple spaces.

    Args:
        header: Raw header string from Excel

    Returns:
        Normalized lowercase string with single spaces

    Examples:
        "  Цена со  скидкой  " -> "цена со скидкой"
        "РРЦ" -> "ррц"
    """
    if not header:
        return ""
    # Trim, lower, collapse multiple spaces
    normalized = str(header).strip().lower()
    normalized = re.sub(r"\s+", " ", normalized)
    return normalized


def _find_matching_field(normalized_header: str) -> str | None:
    """Find standard field name for normalized header.

    Args:
        normalized_header: Normalized header string

    Returns:
        Standard field name or None
    """
    for field_name, aliases in DEFAULT_COLUMN_ALIASES.items():
        for alias in aliases:
            if normalized_header == alias:
                return field_name
    return None


def map_column_aliases(headers: list[str]) -> dict[str, str]:
    """Map Excel headers to standard field names.

    Args:
        headers: List of column headers from Excel

    Returns:
        Mapping of standard_field -> original_excel_header
    """
    mapping: dict[str, str] = {}
    for header in headers:
        normalized = normalize_header_name(header)
        field_name = _find_matching_field(normalized)
        if field_name:
            mapping[field_name] = header
    return mapping


def is_service_row(raw_row: dict[str, Any]) -> bool:
    """Check if row is a service/header row, not a product.

    Service rows have:
    - empty sku
    - empty title
    - price containing currency symbol without number

    Args:
        raw_row: Raw row dictionary from Excel

    Returns:
        True if this is a service row to skip
    """
    sku = raw_row.get("sku")
    title = raw_row.get("title")
    price = raw_row.get("price")

    # Check if sku or title is empty
    if sku is None and title is None:
        return True

    # Check if sku is just whitespace
    if sku is not None and str(sku).strip() == "":
        sku = None

    # Check if title is just whitespace
    if title is not None and str(title).strip() == "":
        title = None

    if sku is None and title is None:
        return True

    # Check if price is just currency symbol (like "₸")
    if price is not None:
        price_str = str(price).strip()
        # If price is just a symbol or very short non-numeric text
        if len(price_str) <= 3 and not any(c.isdigit() for c in price_str):
            return True

    return False


def map_raw_row_to_excel_schema(
    raw_row: dict[str, Any],
    column_mapping: dict[str, str],
    source_file: str = "",
    source_sheet: str = "",
    source_row_index: int = 0,
) -> dict[str, Any] | None:
    """Convert raw row dict to ExcelRowRaw-like structure.

    Skips service rows (currency headers, empty rows).

    Args:
        raw_row: Dictionary from Excel loader
        column_mapping: Mapping of standard fields to original Excel columns
        source_file: Path to source file
        source_sheet: Sheet name
        source_row_index: Row index in source

    Returns:
        Dictionary with mapped fields or None if service row
    """
    # Build row with standard field names
    mapped: dict[str, Any] = {
        "sku": None,
        "title": None,
        "price": None,
        "discount_price": None,
        "stock_qty": None,
        "currency": None,
        "base_attributes": {},
        "source_file": source_file,
        "source_sheet": source_sheet,
        "source_row_index": source_row_index,
    }

    # Map known fields and collect unmapped columns
    mapped_excel_headers = set(column_mapping.values())
    for standard_field, excel_header in column_mapping.items():
        if excel_header in raw_row:
            mapped[standard_field] = raw_row[excel_header]

    # Collect unmapped columns into base_attributes
    base_attributes: dict[str, Any] = {}
    for excel_header, value in raw_row.items():
        if excel_header not in mapped_excel_headers:
            # Skip empty values
            if value is not None and str(value).strip() != "":
                base_attributes[excel_header] = value
    mapped["base_attributes"] = base_attributes

    # Check if this is a service row
    if is_service_row(mapped):
        return None

    return mapped
