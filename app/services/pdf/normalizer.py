"""
Normalization utilities for PDF-extracted data.

Handles text cleaning, whitespace normalization, and value standardization.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Optional

logger = logging.getLogger(__name__)


def normalize_text(text: str | None, max_length: Optional[int] = None) -> str:
    """
    Normalize text: trim, collapse whitespace, remove line breaks.
    
    Args:
        text: Input text
        max_length: Optional max length to truncate to
        
    Returns:
        Cleaned text or empty string
    """
    if not text:
        return ""
    
    # Convert to string and strip
    text = str(text).strip()
    
    # Replace line breaks and multiple spaces with single space
    text = re.sub(r'[\r\n]+', ' ', text)
    text = re.sub(r'\s+', ' ', text)
    
    # Trim again
    text = text.strip()
    
    # Optional length limit
    if max_length and len(text) > max_length:
        text = text[:max_length].rsplit(' ', 1)[0] + '...'
    
    return text


def normalize_sku(sku: str | None) -> Optional[str]:
    """
    Normalize SKU: uppercase, remove extra spaces, clean prefixes.
    
    Args:
        sku: Raw SKU value
        
    Returns:
        Cleaned SKU or None if empty/invalid
    """
    if not sku:
        return None
    
    sku = str(sku).strip().upper()
    
    # Remove common prefixes
    prefixes = ['арт.', 'артикул', 'код', 'code', 'модель', 'model', '№']
    for prefix in prefixes:
        sku = re.sub(rf'^{prefix}[:\s]*', '', sku, flags=re.IGNORECASE)
    
    # Remove extra whitespace
    sku = re.sub(r'\s+', ' ', sku)
    
    # Remove special chars that shouldn't be in SKU
    sku = re.sub(r'[^\w\-\.]', '', sku)
    
    return sku if sku else None


def clean_cell_value(value: Any) -> Optional[str]:
    """
    Clean table cell value: normalize whitespace, handle empty values.
    
    Args:
        value: Raw cell value (can be any type)
        
    Returns:
        Cleaned string or None for empty values
    """
    if value is None:
        return None
    
    # Convert to string
    text = str(value)
    
    # Strip and normalize whitespace
    text = text.strip()
    text = re.sub(r'\s+', ' ', text)
    
    # Empty values
    if not text or text.lower() in ['-', '–', '—', 'null', 'none', 'n/a', '']:
        return None
    
    return text


def normalize_number(value: Any) -> Optional[float | int]:
    """
    Extract numeric value from string.
    
    Handles various formats:
    - 1,234.56
    - 1.234,56
    - 1234
    
    Args:
        value: Raw value
        
    Returns:
        Number or None
    """
    if value is None:
        return None
    
    if isinstance(value, (int, float)):
        return value
    
    text = str(value).strip()
    
    # Remove currency symbols and units
    text = re.sub(r'[^\d\.,\-]', '', text)
    
    if not text:
        return None
    
    # Detect format
    if ',' in text and '.' in text:
        # Assume 1,234.56 format
        if text.rfind(',') > text.rfind('.'):
            # European: 1.234,56
            text = text.replace('.', '').replace(',', '.')
        else:
            # US: 1,234.56
            text = text.replace(',', '')
    elif ',' in text:
        parts = text.split(',')
        if len(parts) == 2 and len(parts[1]) <= 2:
            # Likely decimal: 123,45
            text = text.replace(',', '.')
        else:
            # Thousands separator: 1,234
            text = text.replace(',', '')
    
    try:
        num = float(text)
        # Return int if it's a whole number
        return int(num) if num == int(num) else num
    except ValueError:
        logger.debug(f"Could not parse number from: {value}")
        return None


def extract_units(text: str | None) -> tuple[Optional[float], Optional[str]]:
    """
    Extract numeric value and unit from text.
    
    Example: "200 м" -> (200.0, "м")
    
    Args:
        text: Input text like "200 м" or "10 bar"
        
    Returns:
        Tuple of (number, unit) or (None, None)
    """
    if not text:
        return None, None
    
    text = str(text).strip()
    
    # Match number at start
    match = re.match(r'^([\d\.,]+)\s*(.+)?$', text)
    if not match:
        return None, text
    
    num_str = match.group(1)
    unit = match.group(2)
    
    num = normalize_number(num_str)
    unit = unit.strip() if unit else None
    
    return num, unit