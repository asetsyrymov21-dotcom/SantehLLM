from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

from app.utils.sku_utils import normalize_sku


SKU_PATTERN = re.compile(
    r"\b([A-Za-zА-Яа-я]?\d?[A-Za-z][A-Za-z0-9.-]*\d[A-Za-z0-9.-]*)\b"
)

QTY_WITH_UNIT_PATTERN = re.compile(
    r"\b(\d{1,5})\s*(?:шт|штук|штуки|штука|pcs|pc)\b",
    re.IGNORECASE,
)
QTY_WITH_MARKER_PATTERN = re.compile(r"(?:x|\*)\s*(\d{1,5})\b", re.IGNORECASE)
STANDALONE_NUMBER_PATTERN = re.compile(r"\b(\d{1,5})\b")

STOCK_KEYWORDS = {
    "есть",
    "налич",
    "остат",
    "остаток",
    "сколько",
    "хватит",
    "доступно",
    "est",
    "nalich",
    "ostat",
    "skolko",
    "hvatit",
}
SEARCH_KEYWORDS = {
    "найди",
    "найти",
    "покажи",
    "подбери",
    "варианты",
    "вариант",
    "naydi",
    "naiti",
    "pokazhi",
    "podberi",
    "variant",
}
ADVISORY_KEYWORDS = {
    "комплект",
    "собрать",
    "подойдет",
    "подойдёт",
    "лучше",
    "отличается",
    "аналог",
    "аналоги",
    "нужно",
    "нужны",
    "какие детали",
    "komplekt",
    "komplektuyusch",
    "komplektuiusch",
    "sobrat",
    "podoydet",
    "luchshe",
    "analog",
    "nuzhno",
    "nuzhny",
    "kakie detali",
    "teplogo pola",
}
HELP_KEYWORDS = {
    "как загрузить",
    "загрузить остатки",
    "загрузить каталог",
    "неподдерживаемый бренд",
    "sku не найден",
    "не найден",
    "что значит",
    "как проверить",
    "kak zagruzit",
    "zagruzit ostatki",
    "zagruzit katalog",
    "nepodderzhivaemyi brend",
    "nepodderzhivaemyy brend",
    "sku ne nayden",
    "ne nayden",
    "chto znachit",
    "kak proverit",
}


class AssistantIntent(StrEnum):
    STOCK_CHECK = "stock_check"
    PRODUCT_SEARCH = "product_search"
    ADVISORY_QUESTION = "advisory_question"
    HELP_QUESTION = "help_question"


@dataclass(frozen=True)
class AssistantQuestion:
    text: str
    sku: str | None
    requested_qty: int
    intent: AssistantIntent


def parse_assistant_question(text: str) -> AssistantQuestion:
    """Extract a likely SKU and requested quantity from a manager question."""
    clean_text = (text or "").strip()
    sku = _extract_sku(clean_text)
    qty = _extract_requested_qty(clean_text, sku)
    intent = detect_intent(clean_text, sku=sku)
    return AssistantQuestion(text=clean_text, sku=sku, requested_qty=qty, intent=intent)


def detect_intent(text: str, sku: str | None = None) -> AssistantIntent:
    """Route a manager question to the safest available assistant action."""
    normalized = _normalize_for_intent(text)

    if sku:
        return AssistantIntent.STOCK_CHECK

    if _contains_any_phrase(normalized, HELP_KEYWORDS):
        return AssistantIntent.HELP_QUESTION

    if _contains_any_phrase(normalized, ADVISORY_KEYWORDS):
        return AssistantIntent.ADVISORY_QUESTION

    if _contains_any_phrase(normalized, SEARCH_KEYWORDS):
        return AssistantIntent.PRODUCT_SEARCH

    if _contains_any_phrase(normalized, STOCK_KEYWORDS):
        return AssistantIntent.STOCK_CHECK

    return AssistantIntent.PRODUCT_SEARCH


def _extract_sku(text: str) -> str | None:
    for match in SKU_PATTERN.finditer(text):
        normalized = normalize_sku(match.group(1))
        if normalized and _looks_like_santeh_sku(normalized):
            return normalized
    return None


def _looks_like_santeh_sku(value: str) -> bool:
    if len(value) < 3:
        return False
    if not any(ch.isdigit() for ch in value):
        return False
    if not any(ch.isalpha() for ch in value):
        return False
    return True


def _extract_requested_qty(text: str, sku: str | None) -> int:
    for pattern in (QTY_WITH_UNIT_PATTERN, QTY_WITH_MARKER_PATTERN):
        match = pattern.search(text)
        if match:
            return max(1, int(match.group(1)))

    text_without_sku = text
    if sku:
        text_without_sku = re.sub(
            re.escape(sku), " ", text_without_sku, flags=re.IGNORECASE
        )

    for match in STANDALONE_NUMBER_PATTERN.finditer(text_without_sku):
        return max(1, int(match.group(1)))

    return 1


def _normalize_for_intent(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def _contains_any_phrase(text: str, phrases: set[str]) -> bool:
    return any(phrase in text for phrase in phrases)
