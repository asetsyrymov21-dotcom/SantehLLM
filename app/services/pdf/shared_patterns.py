from __future__ import annotations
import re


# SKU extraction patterns
MAIN_SKU_PATTERN = re.compile(
    r"\b([A-Z]\d{3,}(?:-\d{1,3}[A-Z]?)?)\b",
    re.IGNORECASE,
)
VARIANT_SKU_PATTERN = re.compile(r"\b([A-Z]\d{3,}(?:-\d{1,3}[A-Z]?)*)\b", re.IGNORECASE)

# Words that indicate end of product card or section boundaries
BOUNDARY_WORDS = frozenset(
    [
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
        "GAPPO",
        "FRAP",
    ]
)

# Technical spec indicators
SPEC_INDICATORS = frozenset(
    [
        "размер",
        "вес",
        "мм",
        "кг",
        "bar",
        "латунь",
        "картридж",
        "аэратор",
        "подключение",
        "габариты",
        "упаковка",
    ]
)


ATTRIBUTE_LABELS = frozenset(
    [
        "тип крепления",
        "крепление",
        "подводка",
        "материал",
        "размер упаковки",
        "размер",
        "габариты",
        "вес",
        "картридж",
        "аэратор",
        "подключение",
        "поверхность",
        "покрытие",
        "комплектация",
        "монтаж",
    ]
)
