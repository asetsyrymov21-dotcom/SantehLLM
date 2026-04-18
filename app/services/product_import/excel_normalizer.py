"""Excel data normalization utilities.

Cleans and normalizes values from Excel cells.
"""

from typing import Any

from app.utils.sku_utils import normalize_sku as central_normalize_sku

# Spreadsheet error tokens and junk values to filter from titles
INVALID_TITLE_TOKENS = {
    "#error!",
    "#n/a",
    "#value!",
    "#ref!",
    "#name?",
    "nan",
    "none",
    "",
}


def normalize_sku(raw_value: Any) -> str | None:
    """Normalize SKU value.

    Delegates to central utility for consistency.

    Args:
        raw_value: Raw SKU from Excel

    Returns:
        Cleaned SKU string or None
    """
    return central_normalize_sku(raw_value)


def normalize_price(raw_value: Any) -> float | None:
    """Normalize price value.

    Handles int, float, and string formats like "9520", "9 520", "9,520".
    Returns None if cannot parse.

    Args:
        raw_value: Raw price from Excel (string, number, etc)

    Returns:
        Float price or None
    """
    if raw_value is None:
        return None

    # Already a number
    if isinstance(raw_value, (int, float)):
        if raw_value >= 0:
            return float(raw_value)
        return None

    # String parsing
    if isinstance(raw_value, str):
        # Remove spaces and replace comma with dot
        cleaned = raw_value.replace(" ", "").replace("\xa0", "")
        cleaned = cleaned.replace(",", ".")

        # Try to parse
        try:
            price = float(cleaned)
            if price >= 0:
                return price
        except ValueError:
            pass

    return None


def normalize_stock_qty(raw_value: Any) -> int | None:
    """Normalize stock quantity.

    Note: For advanced parsing with range support (e.g., "10+"),
    use app.utils.stock_parser.parse_stock_value instead.

    Args:
        raw_value: Raw quantity from Excel

    Returns:
        Integer quantity or None
    """
    if raw_value is None:
        return None

    # Already a number
    if isinstance(raw_value, int):
        return raw_value if raw_value >= 0 else None

    if isinstance(raw_value, float):
        return int(raw_value) if raw_value >= 0 else None

    # String parsing
    if isinstance(raw_value, str):
        cleaned = raw_value.strip()
        if cleaned == "":
            return None
        try:
            qty = int(float(cleaned))
            return qty if qty >= 0 else None
        except ValueError:
            pass

    return None


def normalize_attributes(raw_attributes: dict[str, Any]) -> dict[str, Any]:
    """Normalize attribute values.

    Args:
        raw_attributes: Dictionary of raw attribute values

    Returns:
        Cleaned attribute dictionary
    """
    if not raw_attributes:
        return {}

    # Minimal implementation - just return non-empty values
    result = {}
    for key, value in raw_attributes.items():
        if value is not None and str(value).strip() != "":
            result[key] = value

    return result


def _sanitize_title(raw_title: Any) -> str | None:
    """Sanitize title, filtering out spreadsheet errors and junk values.

    Args:
        raw_title: Raw title value from Excel

    Returns:
        Cleaned title or None if invalid/error token
    """
    if raw_title is None:
        return None

    title = str(raw_title).strip()
    if title.lower() in INVALID_TITLE_TOKENS:
        return None

    return title


def normalize_excel_row(mapped_row: dict[str, Any]) -> dict[str, Any]:
    """Normalize complete Excel row from mapped data.

    Args:
        mapped_row: Mapped row with standard field names

    Returns:
        Normalized row dictionary
    """
    return {
        "sku": normalize_sku(mapped_row.get("sku")),
        "title": _sanitize_title(mapped_row.get("title")),  # Filter error tokens
        "price": normalize_price(mapped_row.get("price")),
        "discount_price": normalize_price(mapped_row.get("discount_price")),
        "stock_qty": normalize_stock_qty(mapped_row.get("stock_qty")),
        "currency": mapped_row.get("currency") or "KZT",
        "base_attributes": normalize_attributes(mapped_row.get("base_attributes", {})),
        "source_file": mapped_row.get("source_file", ""),
        "source_sheet": mapped_row.get("source_sheet", ""),
        "source_row_index": mapped_row.get("source_row_index", 0),
        "normalization_errors": [],
    }
