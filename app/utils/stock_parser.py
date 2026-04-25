"""Stock value parsing utilities.

Parses various stock quantity formats from Excel/source files.
Preserves original semantic meaning (e.g., "10+" is not just 10).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional, Union


@dataclass(frozen=True)
class ParsedStockValue:
    """Structured result of parsing a stock value.

    Attributes:
        raw_value: Original raw value from source
        stock_label: Human-readable label (e.g., "10+", "5")
        stock_exact: Exact integer value if parse_status == "exact", else None
        stock_min: Minimum guaranteed stock (for ranges: lower bound, for exact: exact value)
        parse_status: One of: "exact", "range_plus", "range_dash", "empty", "invalid"
    """

    raw_value: Union[str, int, float, None]
    stock_label: str
    stock_exact: Optional[int]
    stock_min: Optional[int]
    parse_status: str

    def is_available(self) -> bool:
        """Check if product has any available stock."""
        if self.parse_status == "empty":
            return False
        if self.parse_status == "invalid":
            return False
        if self.stock_min is not None and self.stock_min > 0:
            return True
        if self.stock_exact is not None and self.stock_exact > 0:
            return True
        return False

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "raw_value": self.raw_value,
            "stock_label": self.stock_label,
            "stock_exact": self.stock_exact,
            "stock_min": self.stock_min,
            "parse_status": self.parse_status,
            "is_available": self.is_available(),
        }


def is_excel_error(value_str: str) -> bool:
    """Check if value is an Excel error token.

    Common Excel errors: #REF!, #N/A, #ERROR!, #VALUE!, #DIV/0!, #NAME?, #NULL!, #NUM!
    """
    if not value_str:
        return False

    error_patterns = [
        r"^#REF!$",
        r"^#N/A$",
        r"^#ERROR!$",
        r"^#VALUE!$",
        r"^#DIV/0!$",
        r"^#NAME\?$",
        r"^#NULL!$",
        r"^#NUM!$",
        r"^#CALC!$",
        r"^#SPILL!$",
        r"^#BUSY!$",
        r"^#\w+!$",  # Generic Excel error pattern
    ]

    upper_val = value_str.upper()
    for pattern in error_patterns:
        if re.match(pattern, upper_val):
            return True
    return False


def parse_stock_value(raw_value: Union[str, int, float, None]) -> ParsedStockValue:
    """Parse stock quantity value from various formats.

    Supported formats:
        - Exact integers: "12", 12, 12.0 -> exact=12, min=12, label="12"
        - Plus ranges: "10+", "30+" -> exact=None, min=10, label="10+"
        - Dash ranges: "5-10" -> exact=None, min=5, label="5-10"
        - Zero: "0", 0 -> exact=0, min=0, label="0"
        - Empty/None/whitespace -> empty (treated as qty=0, not invalid)
        - Excel errors: #REF!, #N/A, #ERROR! -> invalid
        - Other invalid: "abc" -> invalid

    Args:
        raw_value: Raw value from Excel/source

    Returns:
        ParsedStockValue with all fields populated

    Examples:
        >>> parse_stock_value("12")
        ParsedStockValue(raw_value='12', stock_label='12', stock_exact=12, stock_min=12, parse_status='exact')
        >>> parse_stock_value("10+")
        ParsedStockValue(raw_value='10+', stock_label='10+', stock_exact=None, stock_min=10, parse_status='range_plus')
        >>> parse_stock_value("")
        ParsedStockValue(raw_value='', stock_label='', stock_exact=0, stock_min=0, parse_status='empty')
    """
    # Handle None
    if raw_value is None:
        return ParsedStockValue(
            raw_value=None,
            stock_label="",
            stock_exact=0,
            stock_min=0,
            parse_status="empty",
        )

    # Convert to string for uniform processing
    value_str = str(raw_value).strip()

    # Check for empty (None, "", whitespace-only) - treat as qty=0, NOT invalid
    if not value_str or value_str.lower() in ("none", "nan", "null"):
        return ParsedStockValue(
            raw_value=raw_value,
            stock_label="",
            stock_exact=0,
            stock_min=0,
            parse_status="empty",
        )

    # Check for Excel error values - these ARE invalid
    if is_excel_error(value_str):
        return ParsedStockValue(
            raw_value=raw_value,
            stock_label=value_str,
            stock_exact=None,
            stock_min=None,
            parse_status="invalid",
        )

    # Pattern: number followed by plus sign (e.g., "10+", "30+")
    plus_match = re.match(r"^(\d+)\+$", value_str)
    if plus_match:
        min_val = int(plus_match.group(1))
        return ParsedStockValue(
            raw_value=raw_value,
            stock_label=value_str,
            stock_exact=None,
            stock_min=min_val,
            parse_status="range_plus",
        )

    # Pattern: dash range (e.g., "5-10", "3 - 8")
    dash_match = re.match(r"^(\d+)\s*[-–—]\s*(\d+)$", value_str)
    if dash_match:
        min_val = int(dash_match.group(1))
        # max_val = int(dash_match.group(2))  # Not currently used
        return ParsedStockValue(
            raw_value=raw_value,
            stock_label=value_str,
            stock_exact=None,
            stock_min=min_val,
            parse_status="range_dash",
        )

    # Pattern: "больше X" / "more than X" (Russian/English)
    more_than_match = re.match(
        r"^(?:больше|more\s+than|>+)\s*(\d+)$", value_str, re.IGNORECASE
    )
    if more_than_match:
        min_val = int(more_than_match.group(1))
        return ParsedStockValue(
            raw_value=raw_value,
            stock_label=f"{min_val}+",
            stock_exact=None,
            stock_min=min_val,
            parse_status="range_plus",
        )

    # Pattern: clean number (possibly with spaces, commas)
    # Remove spaces and replace comma with dot for decimal handling
    cleaned = value_str.replace(" ", "").replace("\xa0", "").replace(",", ".")

    # Try to parse as integer or float
    try:
        num_val = float(cleaned)
        int_val = int(num_val)

        # Negative values are invalid for stock
        if int_val < 0:
            return ParsedStockValue(
                raw_value=raw_value,
                stock_label=value_str,
                stock_exact=None,
                stock_min=None,
                parse_status="invalid",
            )

        return ParsedStockValue(
            raw_value=raw_value,
            stock_label=str(int_val),
            stock_exact=int_val,
            stock_min=int_val,
            parse_status="exact",
        )
    except ValueError:
        pass

    # If we get here, it's an unrecognized format
    return ParsedStockValue(
        raw_value=raw_value,
        stock_label=value_str,
        stock_exact=None,
        stock_min=None,
        parse_status="invalid",
    )


def parse_stock_value_for_update(
    raw_value: Union[str, int, float, None],
) -> Optional[int]:
    """Parse stock value for direct database update.

    Returns the integer value to store (min for ranges, exact for exact).
    Returns None ONLY for invalid values (Excel errors, non-numeric strings).
    Empty/None values return 0 (qty=0 means no stock).

    Args:
        raw_value: Raw value from source

    Returns:
        Integer value for DB or None if invalid

    Examples:
        >>> parse_stock_value_for_update("12")
        12
        >>> parse_stock_value_for_update("10+")
        10
        >>> parse_stock_value_for_update("")
        0
        >>> parse_stock_value_for_update(None)
        0
        >>> parse_stock_value_for_update("#REF!")
        None
    """
    parsed = parse_stock_value(raw_value)

    # Invalid values return None (caller should skip)
    if parsed.parse_status == "invalid":
        return None

    # For empty, return 0 (stock is zero)
    if parsed.parse_status == "empty":
        return 0

    # For ranges without exact, use stock_min
    if parsed.stock_exact is not None:
        return parsed.stock_exact

    return parsed.stock_min
