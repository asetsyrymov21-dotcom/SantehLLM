from __future__ import annotations
import re
from .classifier import is_valid_sku
from .shared_patterns import MAIN_SKU_PATTERN

BAD_TITLE_MARKERS = frozenset(
    [
        "новинки",
        "серия",
        "каталог",
        "catalog",
        "стр.",
        "страница",
        "page",
        "www.",
        "http",
        "gappo",
        "frap",
    ]
)


def _count_distinct_skus(text: str) -> int:
    seen: set[str] = set()
    for m in MAIN_SKU_PATTERN.finditer(text):
        sku = m.group(1).upper()
        if is_valid_sku(sku):
            seen.add(sku)
    return len(seen)


def _is_bad_title_candidate(candidate: str, main_sku: str) -> bool:
    c = re.sub(r"\s+", " ", candidate).strip()
    if not c:
        return True

    c_lower = c.lower()

    if any(marker in c_lower for marker in BAD_TITLE_MARKERS):
        return True

    if len(c) > 90:
        return True

    if _count_distinct_skus(c) >= 2:
        return True

    if c.upper().count(main_sku.upper()) >= 2:
        return True

    # Reject color/finish-only polluted titles like:
    # "G2406 Матовое розовое золото"
    # "G3006 245 Матовое розовое золото 49"
    tail = c
    if tail.upper().startswith(main_sku.upper()):
        tail = tail[len(main_sku) :].strip(" -,:;")
    tail_lower = tail.lower()

    if not tail:
        return True

    color_markers = [
        "золото",
        "розовое золото",
        "матовое золото",
        "матовое розовое золото",
        "глянцевое золото",
        "хром",
        "черный",
        "чёрный",
        "белый",
        "графит",
        "бронза",
        "сатин",
        "никель",
        "оружейная сталь",
    ]

    product_markers = [
        "смеситель",
        "душевая система",
        "душ",
        "лейка",
        "излив",
        "дозатор",
        "гигиенический душ",
    ]

    # If there is no product noun, but there is a color/finish marker -> bad title
    if any(marker in tail_lower for marker in color_markers) and not any(
        marker in tail_lower for marker in product_markers
    ):
        return True

    # Numeric-heavy garbage like "245 Матовое розовое золото 49"
    digit_chunks = re.findall(r"\b\d+\b", tail)
    if len(digit_chunks) >= 2 and not any(
        marker in tail_lower for marker in product_markers
    ):
        return True

    return False
