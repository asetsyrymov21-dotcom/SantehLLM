from __future__ import annotations

import csv
import os
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import psycopg2
from psycopg2.extras import RealDictCursor


# -----------------------------
# Настройки эвристик
# -----------------------------

TOO_SHORT_WORDS_MAX = 2

GENERIC_PATTERNS = [
    r"^смеситель$",
    r"^стойка$",
    r"^комплект$",
    r"^душевая система$",
    r"^душевой гарнитур$",
    r"^лейка$",
    r"^шланг$",
    r"^излив$",
    r"^держатель$",
    r"^полка$",
    r"^кран$",
]

IMPORTANT_TERMS = {
    "фильтр",
    "питьевой",
    "воды",
    "гигиенический",
    "термостат",
    "термостатический",
    "напольная",
    "напольный",
    "настенная",
    "настенный",
    "встраиваемый",
    "встроенный",
    "для кухни",
    "для ванны",
    "для душа",
    "с гигиеническим душем",
    "с подключением фильтра",
    "для питьевой воды",
}

PRODUCT_TYPE_HINTS = {
    "смеситель": {
        "для",
        "кухни",
        "ванны",
        "душа",
        "раковины",
        "умывальника",
        "фильтр",
        "питьевой",
        "воды",
        "гигиенический",
        "термостат",
        "термостатический",
        "встраиваемый",
        "настенный",
    },
    "стойка": {
        "напольная",
        "настенная",
        "душевая",
        "телескопическая",
    },
    "душевая система": {
        "термостат",
        "термостатическая",
        "встраиваемая",
        "настенная",
    },
}

TRUNCATED_ENDINGS = {
    "для",
    "с",
    "под",
    "и",
    "или",
    "на",
    "в",
    "по",
    "от",
}

REPORTS_DIR = Path("reports")
REPORT_CSV = REPORTS_DIR / "suspicious_product_names.csv"


# -----------------------------
# Модели
# -----------------------------


@dataclass
class ProductRow:
    sku: str
    name: str
    brand: str | None = None


@dataclass
class SuspiciousResult:
    sku: str
    current_name: str
    brand: str | None
    triggered_flags: list[str]
    suspicion_score: float


# -----------------------------
# Нормализация
# -----------------------------


def normalize_text(value: str | None) -> str:
    if not value:
        return ""
    value = value.strip().lower()
    value = re.sub(r"\s+", " ", value)
    return value


def strip_sku_prefix(name: str, sku: str) -> str:
    if not name:
        return ""
    name = name.strip()
    sku = (sku or "").strip()

    if sku and name.lower().startswith(sku.lower() + " "):
        return name[len(sku) :].strip()

    return name


def tokenize(value: str) -> list[str]:
    return re.findall(r"[a-zA-Zа-яА-ЯёЁ0-9-]+", value.lower())


def contains_any_phrase(text: str, phrases: Iterable[str]) -> bool:
    for phrase in phrases:
        if phrase in text:
            return True
    return False


def matches_generic_pattern(text: str) -> bool:
    for pattern in GENERIC_PATTERNS:
        if re.fullmatch(pattern, text):
            return True
    return False


def looks_truncated(text: str) -> bool:
    if not text:
        return False

    stripped = text.strip().lower()
    words = tokenize(stripped)
    if not words:
        return False

    last_word = words[-1]

    if last_word in {"с", "для", "под", "и", "или", "на", "в", "по", "от"}:
        return True

    if stripped.endswith(("/", "-", "(", ",")):
        return True

    if len(last_word) <= 4 and last_word not in {
        "душа",
        "воды",
        "ванны",
        "кухни",
    }:
        if not stripped.endswith(
            (
                "душа",
                "воды",
                "ванны",
                "кухни",
                "раковины",
                "умывальника",
                "полочкой",
            )
        ):
            return True

    return False


def looks_like_source_blob(text: str) -> bool:
    if not text:
        return False

    normalized = text.strip().lower()

    # Слишком длинная строка для нормального product name
    if len(normalized) >= 70:
        return True

    # Слишком много слов
    words = tokenize(normalized)
    if len(words) >= 8:
        return True

    # Явные каталожные / source-маркеры
    blob_markers = [
        "gappo",
        "новинки",
        "латунь",
        "35mm",
        "аксессуаров",
        "смесителей",
        "душевых леек",
        "встраиваемых",
        "гигиенических душей",
    ]
    if any(marker in normalized for marker in blob_markers):
        return True

    return False


def detect_product_type(text: str) -> str | None:
    if "душевая система" in text:
        return "душевая система"
    if "смеситель" in text:
        return "смеситель"
    if "стойка" in text:
        return "стойка"
    return None


# -----------------------------
# БД
# -----------------------------


def get_db_connection():
    """
    Пытаемся читать DSN из DATABASE_URL или из отдельных переменных окружения.
    Подстрой под свой проект, если у тебя уже есть общий db helper.
    """
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        return psycopg2.connect(database_url, cursor_factory=RealDictCursor)

    return psycopg2.connect(
        host=os.getenv("POSTGRES_HOST", "localhost"),
        port=os.getenv("POSTGRES_PORT", "5432"),
        dbname=os.getenv("POSTGRES_DB", "santeh"),
        user=os.getenv("POSTGRES_USER", "postgres"),
        password=os.environ["POSTGRES_PASSWORD"],
        cursor_factory=RealDictCursor,
    )


def fetch_products() -> list[ProductRow]:
    query = """
        SELECT
            sku,
            name,
            brand
        FROM products
        WHERE sku IS NOT NULL
    """

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query)
            rows = cur.fetchall()

    results: list[ProductRow] = []
    for row in rows:
        results.append(
            ProductRow(
                sku=str(row["sku"]).strip(),
                name=(row["name"] or "").strip(),
                brand=(row.get("brand") or "").strip() or None,
            )
        )
    return results


# -----------------------------
# Эвристики
# -----------------------------


def build_name_counter(products: list[ProductRow]) -> Counter[str]:
    counter: Counter[str] = Counter()
    for product in products:
        normalized_name = normalize_text(product.name)
        if normalized_name:
            counter[normalized_name] += 1
    return counter


def score_product(
    product: ProductRow, name_counter: Counter[str]
) -> SuspiciousResult | None:
    original_name = product.name or ""
    cleaned_name = strip_sku_prefix(original_name, product.sku)

    normalized_name = normalize_text(cleaned_name)
    words = tokenize(normalized_name)

    flags: list[str] = []
    score = 0.0

    if not normalized_name:
        flags.append("empty_name")
        score += 1.0
        return SuspiciousResult(
            sku=product.sku,
            current_name=original_name,
            brand=product.brand,
            triggered_flags=flags,
            suspicion_score=round(score, 3),
        )

    if len(words) <= TOO_SHORT_WORDS_MAX:
        flags.append("too_short")
        score += 0.35

    if matches_generic_pattern(normalized_name):
        if normalized_name == "душевая система":
            flags.append("too_generic")
            score += 0.10
        else:
            flags.append("too_generic")
            score += 0.40

    if name_counter[normalized_name] > 1:
        flags.append("duplicate_name")
        score += 0.45

    if looks_truncated(normalized_name):
        flags.append("possibly_truncated")
        score += 0.35

    if looks_like_source_blob(normalized_name):
        flags.append("source_blob_like")
        score += 0.70

    product_type = detect_product_type(normalized_name)

    if product_type == "смеситель":
        has_base_context = any(
            phrase in normalized_name
            for phrase in [
                "для раковины",
                "для умывальника",
                "для кухни",
                "для ванны",
                "для душа",
            ]
        )
        if not has_base_context and len(words) <= 2:
            flags.append("missing_important_terms")
            score += 0.20

    elif product_type == "стойка":
        if len(words) <= TOO_SHORT_WORDS_MAX:
            if normalized_name == "душевая система":
                flags.append("too_short")
                score += 0.10
            else:
                flags.append("too_short")
                score += 0.35

    elif product_type == "душевая система":
        # Базовое имя "душевая система" само по себе допустимо.
        # Флагуем только если есть явный обрыв или совсем странная форма.
        if looks_truncated(normalized_name):
            if "missing_important_terms" not in flags:
                flags.append("missing_important_terms")
                score += 0.10

    if not flags:
        return None

    return SuspiciousResult(
        sku=product.sku,
        current_name=original_name,
        brand=product.brand,
        triggered_flags=flags,
        suspicion_score=round(min(score, 1.0), 3),
    )


def find_suspicious_products(products: list[ProductRow]) -> list[SuspiciousResult]:
    name_counter = build_name_counter(products)
    results: list[SuspiciousResult] = []

    for product in products:
        result = score_product(product, name_counter)
        if result is None:
            continue

        flags = set(result.triggered_flags)

        # Оставляем только реально сломанные строки:
        # source contamination / catalog blob / truncation
        if "source_blob_like" in flags or "possibly_truncated" in flags:
            results.append(result)

    results.sort(
        key=lambda item: (
            -("source_blob_like" in item.triggered_flags),
            -("possibly_truncated" in item.triggered_flags),
            -item.suspicion_score,
            item.current_name.lower(),
            item.sku,
        )
    )
    return results


# -----------------------------
# Вывод
# -----------------------------


def print_top_results(results: list[SuspiciousResult], limit: int = 50) -> None:
    print()
    print(f"Top {min(limit, len(results))} suspicious products:")
    print("-" * 120)
    print(f"{'SKU':20} {'Score':8} {'Flags':45} Name")
    print("-" * 120)

    for item in results[:limit]:
        flags_str = ", ".join(item.triggered_flags)
        print(
            f"{item.sku:20} {item.suspicion_score:<8} {flags_str:45} {item.current_name}"
        )

    print("-" * 120)
    print(f"Total suspicious products: {len(results)}")
    print()


def save_csv(results: list[SuspiciousResult]) -> None:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    with REPORT_CSV.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(
            ["sku", "current_name", "brand", "triggered_flags", "suspicion_score"]
        )

        for item in results:
            writer.writerow(
                [
                    item.sku,
                    item.current_name,
                    item.brand or "",
                    ", ".join(item.triggered_flags),
                    item.suspicion_score,
                ]
            )


# -----------------------------
# Main
# -----------------------------


def main() -> None:
    print("Loading products from database...")
    products = fetch_products()
    print(f"Loaded {len(products)} products")

    results = find_suspicious_products(products)

    print_top_results(results, limit=50)
    save_csv(results)

    print(f"CSV report saved to: {REPORT_CSV}")


if __name__ == "__main__":
    main()
