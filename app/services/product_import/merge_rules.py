"""Merge rules and source priority definitions.

Defines how fields from Excel, PDF, and LLM sources are combined.
"""

from typing import Any


# Source priority constants
SOURCE_EXCEL = "excel"
SOURCE_PDF = "pdf"
SOURCE_LLM = "llm"
SOURCE_MANUAL = "manual"


# Field-level priority rules
# key: field name, value: priority list (first wins)
FIELD_PRIORITY: dict[str, list[str]] = {
    # Excel wins for commercial data
    "sku": [SOURCE_EXCEL, SOURCE_MANUAL],
    "title": [SOURCE_EXCEL, SOURCE_PDF, SOURCE_LLM, SOURCE_MANUAL],
    "price": [SOURCE_EXCEL, SOURCE_MANUAL],
    "discount_price": [SOURCE_EXCEL, SOURCE_MANUAL],
    "stock_qty": [SOURCE_EXCEL, SOURCE_MANUAL],
    "stock_status": [SOURCE_EXCEL, SOURCE_MANUAL],
    "currency": [SOURCE_EXCEL, SOURCE_MANUAL],
    "brand": [SOURCE_EXCEL, SOURCE_PDF, SOURCE_LLM, SOURCE_MANUAL],
    "category": [SOURCE_EXCEL, SOURCE_PDF, SOURCE_LLM, SOURCE_MANUAL],
    # PDF enriches content
    "description": [SOURCE_PDF, SOURCE_LLM, SOURCE_EXCEL, SOURCE_MANUAL],
    "pdf_pages": [SOURCE_PDF, SOURCE_MANUAL],
    "images": [SOURCE_PDF, SOURCE_MANUAL],
    # Attributes merging
    "base_attributes": [SOURCE_EXCEL, SOURCE_PDF, SOURCE_MANUAL],
    "extended_attributes": [SOURCE_PDF, SOURCE_LLM, SOURCE_MANUAL],
}


# Fields that LLM must never overwrite from Excel
LLM_PROTECTED_FIELDS: set[str] = {
    "sku",
    "price",
    "discount_price",
    "stock_qty",
    "stock_status",
    "currency",
}


# Fields where LLM can be used as fallback
LLM_FALLBACK_FIELDS: set[str] = {
    "description",
    "extended_attributes",
    "title",
}


def get_field_priority(field_name: str) -> list[str]:
    """Get source priority list for a field.

    Args:
        field_name: Name of the product field

    Returns:
        Ordered list of source types (first has highest priority)
    """
    # TODO: Handle dynamic priority based on confidence scores
    return FIELD_PRIORITY.get(
        field_name, [SOURCE_EXCEL, SOURCE_PDF, SOURCE_LLM, SOURCE_MANUAL]
    )


def is_llm_allowed_for_field(field_name: str, has_excel_value: bool) -> bool:
    """Check if LLM can provide value for a field.

    Args:
        field_name: Name of the field
        has_excel_value: Whether Excel already has a value

    Returns:
        True if LLM is allowed to provide/suggest value
    """
    # TODO: Add confidence threshold parameter
    if field_name in LLM_PROTECTED_FIELDS:
        return False
    if field_name in LLM_FALLBACK_FIELDS:
        return True
    return not has_excel_value


def resolve_field_value(
    field_name: str,
    excel_value: Any | None,
    pdf_value: Any | None,
    llm_value: Any | None,
    excel_confidence: float = 1.0,
    pdf_confidence: float = 0.8,
    llm_confidence: float = 0.6,
) -> tuple[Any, str, float]:
    """Resolve final value for a field based on priority rules.

    Args:
        field_name: Name of the field to resolve
        excel_value: Value from Excel source (if any)
        pdf_value: Value from PDF source (if any)
        llm_value: Value from LLM source (if any)
        excel_confidence: Confidence in Excel value
        pdf_confidence: Confidence in PDF value
        llm_confidence: Confidence in LLM value

    Returns:
        Tuple of (resolved_value, source_type, confidence)
    """
    # TODO: Implement priority-based resolution with confidence weighting
    # TODO: Handle special cases like partial PDF extractions
    raise NotImplementedError("Field resolution not yet implemented")
