from __future__ import annotations


ATTRIBUTE_LABELS = {
    "цвет",
    "поверхность",
    "высота",
    "длина",
    "ширина",
    "монтаж",
    "материал",
    "гарантия",
}


def is_attribute_context(prefix: str) -> bool:
    """Check if text before SKU looks like attribute context, not title."""
    prefix_lower = prefix.lower().strip()
    if not prefix_lower:
        return False

    return any(
        prefix_lower.endswith(label) or f"{label} " in prefix_lower
        for label in ATTRIBUTE_LABELS
    )


def _is_attribute_context(text: str, start_pos: int, window: int = 80) -> bool:
    """Compatibility helper for legacy PDF card boundary code."""
    prefix = text[max(0, start_pos - window) : start_pos]
    return is_attribute_context(prefix)
