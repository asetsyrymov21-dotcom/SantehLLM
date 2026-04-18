"""
Page type classifier for PDF catalog pages.

Detects page type based on text content heuristics:
- grid_catalog: pages with series headers and dense SKU lists
- product_cards: pages with individual product cards and descriptions
- marketing: image-heavy pages with minimal product text
- unknown: fallback when type cannot be determined
"""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

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
    """Check if token looks like a valid product SKU.

    Args:
        token: String token to check

    Returns:
        True if token matches SKU pattern and is not noise

    """
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


def _has_grid_header_pattern(text: str) -> bool:
    """Check for grid catalog header patterns like 'G52 Серия смесителей...'"""
    return bool(GRID_HEADER_PATTERN.search(text))


def _is_category_index_page(text: str) -> bool:
    """Check for category index pages with multiple groups and page references."""
    if not text or not text.strip():
        return False

    raw_text = text
    normalized = re.sub(r"\s+", " ", text).strip().lower()

    sku_count = _count_skus_in_text(raw_text)
    page_ref_count = len(CATEGORY_PAGE_REF_PATTERN.findall(raw_text))
    has_category_words = any(word in normalized for word in CATEGORY_HEADER_WORDS)

    line_count = len([line for line in raw_text.splitlines() if line.strip()])

    if (
        sku_count >= 6
        and page_ref_count >= 2
        and has_category_words
        and line_count >= 8
    ):
        return True

    return False


def _has_dense_sku_list(text: str, threshold: int = 5) -> bool:
    """Check if text has dense SKU list (many SKUs in short text).

    Args:
        text: Page text
        threshold: Minimum SKU count to consider "dense"

    Returns:
        True if many SKUs found

    """
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    if not lines:
        return False

    # Count SKUs in first ~20 lines
    sample_lines = lines[:20]
    sample_text = " ".join(sample_lines)

    sku_count = _count_skus_in_text(sample_text)

    # Check for SKU density - many SKUs without much description
    words = sample_text.split()
    non_sku_words = [w for w in words if not is_valid_sku(w)]

    # Grid pages have high SKU-to-text ratio
    if sku_count >= threshold and len(non_sku_words) < sku_count * 3:
        return True

    return False


def _has_product_descriptors(text: str) -> bool:
    """Check for product card descriptors like 'Смеситель', 'латунь', etc."""
    text_lower = text.lower()
    found = sum(1 for word in DESCRIPTOR_WORDS if word in text_lower)
    return found >= 2  # At least 2 descriptors


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


def detect_page_type(text: str, page_number: int = 0) -> str:
    """
    Detect the type of PDF catalog page based on content heuristics.

    Args:
        text: Extracted text from the page
        page_number: Page number for debug output (optional)

    Returns:
        One of: "grid_catalog", "category_index", "product_cards", "marketing", "unknown"
    """
    if not text or not text.strip():
        print(f"PAGE {page_number}: final_type=marketing (empty text)")
        logger.debug("Page classified as marketing (empty text)")
        return "marketing"

    raw_text = text
    normalized_text = re.sub(r"\s+", " ", text).strip()

    # Marketing: лучше смотреть по raw_text, чтобы не потерять реальную структуру страницы

    # Grid catalog: здесь нормализованный текст полезен, потому что заголовок и SKU
    # часто идут одной длинной строкой
    has_header = _has_grid_header_pattern(normalized_text)
    has_dense_skus = _has_dense_sku_list(raw_text, threshold=5)

    if has_header and has_dense_skus:
        print(
            f"PAGE {page_number}: final_type=grid_catalog (header={has_header}, dense_skus={has_dense_skus})"
        )
        logger.debug("Page classified as grid_catalog (header + dense SKUs)")
        return "grid_catalog"

    # if _is_category_index_page(raw_text):
    #    logger.debug("Page classified as category_index (category overview page)")
    #     return "category_index"

    # Product cards:
    # - структуру лучше смотреть по raw_text
    # - дескрипторы и sku_count можно по normalized_text
    has_descriptors = _has_product_descriptors(normalized_text)
    has_card_structure = _has_card_structure(raw_text)
    has_repeated_blocks = _has_repeated_product_blocks(raw_text)
    sku_count = _count_skus_in_text(normalized_text)

    if _is_likely_marketing(raw_text):
        print(f"PAGE {page_number}: final_type=marketing")
        logger.debug("Page classified as marketing (low text, no SKUs)")
        return "marketing"

    if has_card_structure:
        print(f"PAGE {page_number}: final_type=product_cards (card_structure)")
        logger.debug("Page classified as product_cards (card structure detected)")
        return "product_cards"

    if has_repeated_blocks:
        print(f"PAGE {page_number}: final_type=product_cards (repeated_blocks)")
        logger.debug("Page classified as product_cards (repeated product blocks)")
        return "product_cards"

    if sku_count >= 2 and has_descriptors and not has_dense_skus:
        print(f"PAGE {page_number}: final_type=product_cards (sku+desc)")
        logger.debug("Page classified as product_cards (SKU + descriptors fallback)")
        return "product_cards"

    # Fallback for OCR/text-collapse pages:
    # page looks product-like because it has several SKUs,
    # but structure/descriptors were lost when text collapsed into one line.
    text_lines = len([l for l in text.split("\n") if l.strip()])

    # Fallback for overview/grid pages where PDF text collapsed into one line:
    # many SKUs, almost no descriptors, no card structure.
    if (
        sku_count >= 10
        and text_lines <= 2
        and not has_descriptors
        and not has_card_structure
    ):
        print(
            f"PAGE {page_number}: final_type=grid_catalog "
            f"(fallback_many_skus_collapsed_overview)"
        )
        logger.debug(
            "Page classified as grid_catalog " "(many SKUs collapsed overview fallback)"
        )
        return "grid_catalog"

    if (
        sku_count >= 2
        and text_lines <= 2
        and len(normalized_text) >= 200
        and not has_header
    ):
        print(
            f"PAGE {page_number}: final_type=product_cards "
            f"(fallback_collapsed_text_with_skus)"
        )
        logger.debug(
            "Page classified as product_cards "
            "(collapsed text with multiple SKUs fallback)"
        )
        return "product_cards"

    if sku_count >= 10 and has_header:
        print(f"PAGE {page_number}: final_type=grid_catalog (fallback)")
        logger.debug("Page classified as grid_catalog (SKUs + header fallback)")
        return "grid_catalog"

    if has_dense_skus and not has_card_structure:
        print(
            f"PAGE {page_number}: final_type=grid_catalog "
            f"(fallback_dense_skus_without_card_structure)"
        )
        logger.debug(
            "Page classified as grid_catalog "
            "(dense SKUs without card structure fallback)"
        )
        return "grid_catalog"

    if sku_count == 0 and has_descriptors and not has_card_structure:
        print(
            f"PAGE {page_number}: final_type=marketing "
            f"(fallback_descriptive_without_sku)"
        )
        logger.debug(
            "Page classified as marketing "
            "(descriptive content without SKU/card structure fallback)"
        )
        return "marketing"

    if (
        not has_header
        and not has_dense_skus
        and not has_card_structure
        and sku_count <= 1
        and len(normalized_text) >= 250
    ):
        print(
            f"PAGE {page_number}: final_type=marketing "
            f"(fallback_sparse_marketing_page)"
        )
        logger.debug("Page classified as marketing " "(sparse marketing page fallback)")
        return "marketing"

    if sku_count == 0 and not has_descriptors and text_lines <= 2:
        print(f"PAGE {page_number}: final_type=marketing (image_like_page)")
        logger.debug("Page classified as marketing (image-like page fallback)")
        return "marketing"

    # Debug output for unknown pages
    print(f"PAGE {page_number}: final_type=unknown")
    print(f"  signals:")
    print(f"    has_grid_header={has_header}")
    print(f"    has_dense_skus={has_dense_skus} (sku_count={sku_count})")
    print(f"    has_descriptors={has_descriptors}")
    print(f"    has_repeated_blocks={has_repeated_blocks}")
    print(f"    has_card_structure={has_card_structure}")
    print(f"    text_lines={len([l for l in text.split(chr(10)) if l.strip()])}")
    print(f"    text_length={len(normalized_text)}")
    logger.debug("Page type unknown (no clear patterns matched)")
    return "unknown"
