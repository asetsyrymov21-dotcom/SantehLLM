#!/usr/bin/env python3
"""
Audit unmatched SKUs from stock import.

Analyzes unmatched.csv to determine if SKUs are truly missing
or if there's a normalization issue, including engineering-style
SKU formats like F101.2006 / F101-2006.
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import func

from app.db.models import Product
from app.db.session import SessionLocal


REPORTS_DIR = Path("reports/products_audit/unmatched_audit")


def ensure_reports_dir() -> None:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)


@contextmanager
def get_db_session():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


def write_csv(filepath: Path, rows: list[dict], fieldnames: list[str]) -> None:
    with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def normalize_sku_simple(sku: str) -> str:
    return sku.strip().upper().replace(" ", "")


def normalize_sku_extended(sku: str) -> str:
    return sku.strip().upper().replace(" ", "").replace(".", "").replace("-", "")


def find_sku_column(reader: csv.DictReader) -> str:
    possible_columns = ["sku_normalized", "normalized_sku", "sku", "SKU"]

    fieldnames = list(reader.fieldnames or [])
    for col in possible_columns:
        if col in fieldnames:
            return col

    raise ValueError(
        f"Could not find SKU column in CSV. "
        f"Expected one of: {possible_columns}. "
        f"Found columns: {fieldnames}"
    )


def read_unmatched_skus(filepath: Path) -> list[str]:
    with open(filepath, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)

        if not reader.fieldnames:
            raise ValueError("CSV file is empty or has no headers")

        sku_column = find_sku_column(reader)

        skus: list[str] = []
        for row in reader:
            sku = (row.get(sku_column) or "").strip()
            if sku:
                skus.append(sku)

        return skus


def build_product_indexes(
    session,
) -> tuple[dict[str, object], dict[str, object], dict[str, object]]:
    products = session.query(Product.id, Product.sku, Product.name, Product.brand).all()

    exact_map: dict[str, object] = {}
    simple_map: dict[str, object] = {}
    extended_map: dict[str, object] = {}

    for product in products:
        sku = (product.sku or "").strip()
        if not sku:
            continue

        exact_map.setdefault(sku, product)
        simple_map.setdefault(normalize_sku_simple(sku), product)
        extended_map.setdefault(normalize_sku_extended(sku), product)

    return exact_map, simple_map, extended_map


def analyze_unmatched_skus(session, skus: list[str]) -> dict[str, list[dict]]:
    exact_found: list[dict] = []
    normalized_found: list[dict] = []
    truly_missing: list[dict] = []

    exact_map, simple_map, extended_map = build_product_indexes(session)

    for sku in skus:
        # 1. Exact match
        product = exact_map.get(sku)
        if product:
            exact_found.append(
                {
                    "source_sku": sku,
                    "matched_product_id": product.id,
                    "matched_product_sku": product.sku,
                    "matched_product_name": product.name,
                    "matched_product_brand": product.brand,
                    "match_type": "exact",
                }
            )
            continue

        # 2. Case-insensitive / simple normalized match
        simple_key = normalize_sku_simple(sku)
        product = simple_map.get(simple_key)
        if product:
            match_type = (
                "case_insensitive"
                if (product.sku or "").upper() == sku.upper()
                else "normalized_simple"
            )
            normalized_found.append(
                {
                    "source_sku": sku,
                    "matched_product_id": product.id,
                    "matched_product_sku": product.sku,
                    "matched_product_name": product.name,
                    "matched_product_brand": product.brand,
                    "match_type": match_type,
                }
            )
            continue

        # 3. Extended normalized match for engineering-style SKUs
        extended_key = normalize_sku_extended(sku)
        product = extended_map.get(extended_key)
        if product:
            normalized_found.append(
                {
                    "source_sku": sku,
                    "matched_product_id": product.id,
                    "matched_product_sku": product.sku,
                    "matched_product_name": product.name,
                    "matched_product_brand": product.brand,
                    "match_type": "normalized_extended",
                }
            )
            continue

        # 4. Truly missing
        truly_missing.append({"source_sku": sku})

    return {
        "exact_found": exact_found,
        "normalized_found": normalized_found,
        "truly_missing": truly_missing,
    }


def generate_prefix_summary(skus: list[str]) -> list[dict]:
    prefixes = Counter()
    for sku in skus:
        if sku:
            prefixes[sku[0].upper()] += 1

    return [
        {"prefix": prefix, "total": total} for prefix, total in sorted(prefixes.items())
    ]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Audit unmatched SKUs from stock import"
    )
    parser.add_argument(
        "--unmatched-file",
        required=True,
        help="Path to unmatched.csv file from stock import",
    )
    args = parser.parse_args()

    unmatched_file = Path(args.unmatched_file)
    if not unmatched_file.exists():
        print(f"Error: File not found: {unmatched_file}")
        sys.exit(1)

    print(f"Reading unmatched SKUs from: {unmatched_file}")
    try:
        skus = read_unmatched_skus(unmatched_file)
    except ValueError as e:
        print(f"Error reading CSV: {e}")
        sys.exit(1)

    total_unmatched_rows = len(skus)
    distinct_skus = len(set(skus))

    print(f"Total unmatched rows: {total_unmatched_rows}")
    print(f"Distinct SKUs: {distinct_skus}")

    ensure_reports_dir()

    with get_db_session() as session:
        results = analyze_unmatched_skus(session, skus)

    prefix_summary = generate_prefix_summary(skus)

    if results["exact_found"]:
        write_csv(
            REPORTS_DIR / "unmatched_found_exact.csv",
            results["exact_found"],
            [
                "source_sku",
                "matched_product_id",
                "matched_product_sku",
                "matched_product_name",
                "matched_product_brand",
                "match_type",
            ],
        )
        print(
            f"Wrote {len(results['exact_found'])} exact matches to unmatched_found_exact.csv"
        )

    if results["normalized_found"]:
        write_csv(
            REPORTS_DIR / "unmatched_possible_normalization_match.csv",
            results["normalized_found"],
            [
                "source_sku",
                "matched_product_id",
                "matched_product_sku",
                "matched_product_name",
                "matched_product_brand",
                "match_type",
            ],
        )
        print(
            f"Wrote {len(results['normalized_found'])} normalization matches "
            f"to unmatched_possible_normalization_match.csv"
        )

    write_csv(
        REPORTS_DIR / "unmatched_exact_missing.csv",
        results["truly_missing"],
        ["source_sku"],
    )
    print(
        f"Wrote {len(results['truly_missing'])} truly missing SKUs to unmatched_exact_missing.csv"
    )

    write_csv(
        REPORTS_DIR / "unmatched_prefix_summary.csv",
        prefix_summary,
        ["prefix", "total"],
    )
    print(
        f"Wrote prefix summary ({len(prefix_summary)} rows) to unmatched_prefix_summary.csv"
    )

    print("\n" + "=" * 50)
    print("SUMMARY")
    print("=" * 50)
    print(f"Total unmatched rows:      {total_unmatched_rows}")
    print(f"Distinct SKUs:             {distinct_skus}")
    print(f"Exact matches found:       {len(results['exact_found'])}")
    print(f"Normalized matches found:  {len(results['normalized_found'])}")
    print(f"Truly missing:             {len(results['truly_missing'])}")
    print(f"Prefix summary rows:       {len(prefix_summary)}")
    print(f"\nReports saved to: {REPORTS_DIR.absolute()}")
    print("=" * 50)


if __name__ == "__main__":
    main()
