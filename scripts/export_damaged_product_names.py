from __future__ import annotations

import csv
import os
import re
from dataclasses import dataclass
from pathlib import Path

import psycopg2
from psycopg2.extras import RealDictCursor


REPORTS_DIR = Path("reports")
REPORT_CSV = REPORTS_DIR / "damaged_product_names.csv"


@dataclass
class ProductRow:
    sku: str
    name: str
    brand: str | None = None


@dataclass
class DamagedRow:
    sku: str
    name: str
    brand: str | None
    cluster_hint: str
    damage_type: str
    matched_markers: str


def normalize_text(value: str | None) -> str:
    if not value:
        return ""
    value = value.strip().lower()
    value = re.sub(r"\s+", " ", value)
    return value


def tokenize(value: str) -> list[str]:
    return re.findall(r"[a-zA-Zа-яА-ЯёЁ0-9-]+", value.lower())


def strip_sku_prefix(name: str, sku: str) -> str:
    if not name:
        return ""
    name = name.strip()
    sku = (sku or "").strip()

    if sku and name.lower().startswith(sku.lower() + " "):
        return name[len(sku) :].strip()

    return name


def get_db_connection():
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
            NULL AS brand
        FROM products
        WHERE sku IS NOT NULL
          AND name IS NOT NULL
          AND btrim(name) <> ''
    """

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query)
            rows = cur.fetchall()

    products: list[ProductRow] = []
    for row in rows:
        products.append(
            ProductRow(
                sku=str(row["sku"]).strip(),
                name=(row["name"] or "").strip(),
                brand=(row.get("brand") or "").strip() or None,
            )
        )
    return products


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

    if len(last_word) <= 3 and last_word not in {
        "для",
        "душа",
        "воды",
        "ванны",
        "кухни",
    }:
        return True

    suspicious_suffixes = (
        "дл",
        "пе",
        "поло",
        "ц",
        "на",
    )
    if last_word.endswith(suspicious_suffixes):
        return True

    return False


BLOB_RULES: list[tuple[str, list[str], str, str]] = [
    (
        "g103_mixers_35mm",
        ["смесителей", "35mm"],
        "catalog_blob",
        "G103 / mixers / 35mm blob",
    ),
    (
        "shower_heads_blob",
        ["душевых леек"],
        "catalog_blob",
        "shower heads blob",
    ),
    (
        "accessories_blob",
        ["аксессуаров"],
        "catalog_blob",
        "accessories blob",
    ),
    (
        "hygienic_showers_blob",
        ["гигиенических душей"],
        "catalog_blob",
        "hygienic showers blob",
    ),
    (
        "embedded_showers_blob",
        ["встраиваемых", "душей"],
        "catalog_blob",
        "embedded showers blob",
    ),
    (
        "novinki_blob",
        ["новинки"],
        "catalog_blob",
        "novinki blob",
    ),
    (
        "gappo_blob",
        ["gappo"],
        "catalog_blob",
        "gappo blob",
    ),
    (
        "shower_system_mixers_blob",
        ["душевая система", "излив"],
        "mixed_blob_and_name",
        "shower system + spout mixed text",
    ),
]


def detect_blob_cluster(text: str) -> tuple[str | None, str | None, list[str]]:
    matched_markers: list[str] = []

    for cluster_hint, markers, damage_type, _description in BLOB_RULES:
        if all(marker in text for marker in markers):
            matched_markers.extend(markers)
            return cluster_hint, damage_type, sorted(set(matched_markers))

    generic_markers = [
        "gappo",
        "новинки",
        "35mm",
        "смесителей",
        "душевых леек",
        "аксессуаров",
        "гигиенических душей",
        "встраиваемых",
    ]
    found = [marker for marker in generic_markers if marker in text]
    if found:
        return "generic_catalog_blob", "catalog_blob", sorted(set(found))

    return None, None, []


def classify_damage(product: ProductRow) -> DamagedRow | None:
    original_name = product.name or ""
    cleaned_name = strip_sku_prefix(original_name, product.sku)
    normalized = normalize_text(cleaned_name)

    if not normalized:
        return DamagedRow(
            sku=product.sku,
            name=original_name,
            brand=product.brand,
            cluster_hint="empty_name",
            damage_type="empty_name",
            matched_markers="",
        )

    cluster_hint, blob_damage_type, matched_markers = detect_blob_cluster(normalized)
    truncated = looks_truncated(normalized)

    if cluster_hint and truncated:
        return DamagedRow(
            sku=product.sku,
            name=original_name,
            brand=product.brand,
            cluster_hint=cluster_hint,
            damage_type="mixed_blob_and_name",
            matched_markers=", ".join(matched_markers),
        )

    if cluster_hint:
        return DamagedRow(
            sku=product.sku,
            name=original_name,
            brand=product.brand,
            cluster_hint=cluster_hint,
            damage_type=blob_damage_type or "catalog_blob",
            matched_markers=", ".join(matched_markers),
        )

    if truncated:
        return DamagedRow(
            sku=product.sku,
            name=original_name,
            brand=product.brand,
            cluster_hint="truncated_only",
            damage_type="truncated_name",
            matched_markers="",
        )

    return None


def collect_damaged_rows(products: list[ProductRow]) -> list[DamagedRow]:
    results: list[DamagedRow] = []

    for product in products:
        damaged = classify_damage(product)
        if damaged is not None:
            results.append(damaged)

    damage_priority = {
        "mixed_blob_and_name": 0,
        "catalog_blob": 1,
        "truncated_name": 2,
        "empty_name": 3,
    }

    results.sort(
        key=lambda item: (
            damage_priority.get(item.damage_type, 99),
            item.cluster_hint,
            item.name.lower(),
            item.sku,
        )
    )
    return results


def save_csv(rows: list[DamagedRow]) -> None:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    with REPORT_CSV.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(
            ["sku", "name", "brand", "cluster_hint", "damage_type", "matched_markers"]
        )

        for row in rows:
            writer.writerow(
                [
                    row.sku,
                    row.name,
                    row.brand or "",
                    row.cluster_hint,
                    row.damage_type,
                    row.matched_markers,
                ]
            )


def print_summary(rows: list[DamagedRow]) -> None:
    by_type: dict[str, int] = {}
    by_cluster: dict[str, int] = {}

    for row in rows:
        by_type[row.damage_type] = by_type.get(row.damage_type, 0) + 1
        by_cluster[row.cluster_hint] = by_cluster.get(row.cluster_hint, 0) + 1

    print()
    print(f"Damaged rows found: {len(rows)}")
    print()

    print("By damage_type:")
    for damage_type, count in sorted(by_type.items(), key=lambda x: (-x[1], x[0])):
        print(f"  {damage_type:20} {count}")

    print()
    print("Top clusters:")
    for cluster_hint, count in sorted(by_cluster.items(), key=lambda x: (-x[1], x[0]))[
        :20
    ]:
        print(f"  {cluster_hint:25} {count}")

    print()
    print("Top 50 rows:")
    print("-" * 140)
    print(f"{'SKU':20} {'damage_type':22} {'cluster_hint':25} Name")
    print("-" * 140)

    for row in rows[:50]:
        print(f"{row.sku:20} {row.damage_type:22} {row.cluster_hint:25} {row.name}")

    print("-" * 140)
    print()


def main() -> None:
    print("Loading products from database...")
    products = fetch_products()
    print(f"Loaded {len(products)} products")

    damaged_rows = collect_damaged_rows(products)
    print_summary(damaged_rows)
    save_csv(damaged_rows)

    print(f"CSV report saved to: {REPORT_CSV}")


if __name__ == "__main__":
    main()
