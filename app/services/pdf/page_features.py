"""Page feature detection for PDF extraction routing.

This module provides feature detection functions used by the router
to make extraction strategy decisions.
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

    from .extraction_types import PageFeatures
    from .page_types import PageType

logger = logging.getLogger(__name__)

# SKU pattern for valid product SKUs (letter + digits + optional suffix)
SKU_PATTERN = re.compile(
    r"^[A-Z]{1,3}\d{2,5}(?:-\d{1,3}[A-Z0-9]?)?$",
    re.IGNORECASE,
)

# Grid catalog patterns
GRID_HEADER_PATTERN = re.compile(
    r"[A-ZА-Я][A-ZА-Я0-9-]*\s+Серия\s+смесителей.*?стр\.\s*\d+",
    flags=re.IGNORECASE,
)

CATEGORY_PAGE_REF_PATTERN = re.compile(r"\bстр\.?\s*\d+\b", re.IGNORECASE)
CATEGORY_HEADER_WORDS = (
    "комплектующие",
    "аксессуары",
    "лейки",
    "душевые гарнитуры",
    "душевые системы",
    "изливы",
    "держатели",
    "шланги",
    "переключатели",
)

# Product card patterns
DESCRIPTOR_WORDS = frozenset(
    [
        "смеситель",
        "смесители",
        "дозатор",
        "дозаторы",
        "для раковины",
        "для ванны",
        "для душа",
        "для кухни",
        "латунь",
        "хром",
        "матовый",
        "черный",
        "золотой",
        "бронза",
        "размер упаковки",
        "габариты",
        "вес",
        "материал",
        "поверхность",
        "покрытие",
        "картридж",
        "аэратор",
        "гарантия",
        "комплектация",
        "монтаж",
        "подключение",
        "водосбережение",
        "экологичность",
        "сертификат",
    ]
)

# Marketing page patterns
MARKETING_KEYWORDS = frozenset(
    [
        "качество",
        "стиль",
        "дизайн",
        "инновации",
        "лидер",
        "премиум",
        "гарантия",
        "доверие",
        "выбор",
        "professionals",
        "since",
        "since 19",
        "основан",
        "традиции",
        "будущее",
        "комфорт",
        "надежность",
        "эксклюзив",
        "limited",
        "edition",
        "new",
        "collection",
        "коллекция",
        "страница",
        "www.",
        "http",
        "tel:",
        "телефон",
        "адрес",
        "контакты",
        "contact",
        "about us",
    ]
)

# Noise patterns to exclude from SKU detection
NOISE_PATTERNS = frozenset(
    [
        r"^\d+$",  # pure numbers
        r"^\d+mm$",  # measurements like 25mm, 300mm
        r"^\d+ml$",  # volume like 300ml
        r"^\d+bar$",  # pressure
        r"^PCS$",  # piece count
        r"^шт\.?$",  # штуки
        r"^мм\.?$",  # миллиметры
        r"^см\.?$",  # сантиметры
        r"^м\.?$",  # метры
        r"^кг\.?$",  # килограммы
        r"^г\.?$",  # граммы
    ]
)


def is_valid_sku(token: str) -> bool:
    """Check if token looks like a valid product SKU."""
    token = token.strip().upper()
    if not token or len(token) < 2:
        return False

    # Check against noise patterns first
    for pattern in NOISE_PATTERNS:
        if re.match(pattern, token, re.IGNORECASE):
            return False

    # Check main SKU pattern
    if not SKU_PATTERN.match(token):
        return False

    return True


def _count_skus_in_text(text: str) -> int:
    """Count valid SKU-like tokens in text."""
    tokens = re.findall(
        r"\b[A-Z]{1,3}\d{2,5}(?:-\d{1,3}[A-Z0-9]?)?\b",
        text,
        re.IGNORECASE,
    )
    valid_count = sum(1 for t in tokens if is_valid_sku(t))
    return valid_count


def _extract_distinct_skus(text: str) -> list[str]:
    """Extract list of distinct valid SKUs from text."""
    tokens = re.findall(
        r"\b[A-Z]{1,3}\d{2,5}(?:-\d{1,3}[A-Z0-9]?)?\b",
        text,
        re.IGNORECASE,
    )
    seen: set[str] = set()
    distinct: list[str] = []
    for t in tokens:
        if is_valid_sku(t):
            upper = t.upper()
            if upper not in seen:
                seen.add(upper)
                distinct.append(upper)
    return distinct


def _has_grid_header_pattern(text: str) -> bool:
    """Check for grid catalog header patterns like 'G52 Серия смесителей...'"""
    return bool(GRID_HEADER_PATTERN.search(text))


def _has_product_descriptors(text: str) -> bool:
    """Check for product card descriptors like 'Смеситель', 'латунь', etc."""
    text_lower = text.lower()
    found = sum(1 for word in DESCRIPTOR_WORDS if word in text_lower)
    return found >= 2  # At least 2 descriptors


def _has_card_structure(text: str) -> bool:
    """Check for product card structure (SKU followed by descriptive content)."""
    lines = [l.strip() for l in text.split("\n") if l.strip()]

    # Если PDF дал переносы строк
    if len(lines) >= 2:
        for i, line in enumerate(lines):
            sku_match = re.match(
                r"^([A-Z]{1,3}\d{2,5}(?:-\d{1,3}[A-Z0-9]?)?)\b",
                line,
                re.IGNORECASE,
            )
            if not sku_match:
                continue

            next_lines = lines[i + 1 : i + 5]
            description_score = 0.0

            for next_line in next_lines:
                if _has_product_descriptors(next_line):
                    description_score += 1
                if len(next_line) > 15 and not is_valid_sku(next_line[:12]):
                    description_score += 0.5

            # Раньше тут по сути требовалось слишком много
            if description_score >= 1:
                return True

    # Fallback: если текст схлопнулся в одну строку
    normalized = re.sub(r"\s+", " ", text).strip()
    sku_count = _count_skus_in_text(normalized)
    if sku_count < 1:
        return False
    if _has_product_descriptors(normalized):
        return True
    return False


def _has_repeated_product_blocks(text: str) -> bool:
    """Detect repeated vertical product blocks with SKU + short description."""
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    if len(lines) < 4:
        return False

    block_hits = 0
    for i, line in enumerate(lines):
        sku_match = re.match(
            r"^([A-Z]{1,3}\d{2,5}(?:-\d{1,3}[A-Z0-9]?)?)\b",
            line,
            re.IGNORECASE,
        )
        if not sku_match:
            continue

        next_lines = lines[i + 1 : i + 4]
        local_score = 0
        for next_line in next_lines:
            if len(next_line) > 8:
                local_score += 1
            if _has_product_descriptors(next_line):
                local_score += 1

        if local_score >= 1:
            block_hits += 1

    return block_hits >= 2


def _is_likely_marketing(text: str) -> bool:
    """Check if page appears to be marketing/image page."""
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    normalized = re.sub(r"\s+", " ", text).strip()

    # Очень мало текста
    if len(lines) <= 2 and len(normalized) < 300:
        return True
    if len(normalized) < 120:
        return True

    text_lower = normalized.lower()
    marketing_score = sum(2 for word in MARKETING_KEYWORDS if word in text_lower)
    sku_count = _count_skus_in_text(normalized)

    # Маркетинговая страница = мало SKU и есть рекламные/имиджевые слова
    if marketing_score >= 3 and sku_count < 3:
        return True

    return False


def _estimate_columns(text: str) -> int:
    """Estimate number of columns in page layout."""
    lines = [l for l in text.split("\n") if l.strip()]
    if len(lines) < 3:
        return 1

    # Simple heuristic: check for alignment patterns
    # More sophisticated column detection could be added here
    return 1


def extract_page_features(text: str, page_number: int = 0) -> "PageFeatures":
    """Extract all features from a page for routing decisions."""
    from .extraction_types import PageFeatures

    raw_text = text
    normalized_text = re.sub(r"\s+", " ", text).strip() if text else ""
    lines = [l for l in text.split("\n") if l.strip()] if text else []
    distinct_skus = _extract_distinct_skus(text) if text else []

    line_count = len(lines)
    text_length = len(normalized_text)
    sku_count = len(distinct_skus)

    # Calculate SKU density
    sku_density = sku_count / line_count if line_count > 0 else 0.0

    # Detect features
    has_line_breaks = line_count > 2
    estimated_columns = _estimate_columns(text) if text else 1
    has_product_descriptors = (
        _has_product_descriptors(normalized_text) if text else False
    )
    has_grid_header = _has_grid_header_pattern(normalized_text) if text else False
    has_card_structure = _has_card_structure(raw_text) if text else False
    has_repeated_blocks = _has_repeated_product_blocks(raw_text) if text else False

    return PageFeatures(
        text=text or "",
        normalized_text=normalized_text,
        text_length=text_length,
        line_count=line_count,
        sku_count=sku_count,
        sku_density=sku_density,
        distinct_skus=distinct_skus,
        has_line_breaks=has_line_breaks,
        estimated_columns=estimated_columns,
        has_product_descriptors=has_product_descriptors,
        has_grid_header=has_grid_header,
        has_card_structure=has_card_structure,
        has_repeated_blocks=has_repeated_blocks,
        page_number=page_number,
    )
