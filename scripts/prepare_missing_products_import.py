#!/usr/bin/env python3
"""
Prepare CSV for importing confirmed-missing products into catalog.

Input:
- reports/products_audit/unmatched_audit/unmatched_exact_missing.csv

Output:
- reports/products_audit/missing_products_audit/prepare_missing_products_import.csv

Notes:
- This is a preparation step only
- No DB access
- No writes outside CSV reports
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path


REPORTS_DIR = Path("reports/products_audit/missing_products_audit")
OUTPUT_FILE = REPORTS_DIR / "prepare_missing_products_import.csv"


def ensure_reports_dir() -> None:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)


def read_missing_skus(input_file: Path) -> list[str]:
    with open(input_file, "r", newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)

        if not reader.fieldnames:
            raise ValueError("CSV file is empty or has no headers")

        if "source_sku" not in reader.fieldnames:
            raise ValueError(
                f"Column 'source_sku' not found. Found columns: {reader.fieldnames}"
            )

        skus: list[str] = []
        for row in reader:
            sku = (row.get("source_sku") or "").strip()
            if sku:
                skus.append(sku)

    return skus


def get_expected_brand(sku: str) -> str:
    sku_upper = sku.strip().upper()
    if sku_upper.startswith("F"):
        return "FRAP"
    if sku_upper.startswith("G"):
        return "GAPPO"
    return "UNKNOWN"


def build_rows(skus: list[str]) -> list[dict]:
    rows: list[dict] = []

    for sku in skus:
        brand = get_expected_brand(sku)
        rows.append(
            {
                "sku": sku,
                "brand": brand,
                "name": "",
                "source": "missing_from_stock_audit",
                "needs_name_fill": 1,
            }
        )

    return rows


def write_csv(output_file: Path, rows: list[dict]) -> None:
    fieldnames = ["sku", "brand", "name", "source", "needs_name_fill"]

    with open(output_file, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def print_summary(rows: list[dict]) -> None:
    total_rows = len(rows)
    frap_rows = sum(1 for row in rows if row["brand"] == "FRAP")
    gappo_rows = sum(1 for row in rows if row["brand"] == "GAPPO")
    unknown_rows = sum(1 for row in rows if row["brand"] == "UNKNOWN")

    print("\n" + "=" * 50)
    print("SUMMARY")
    print("=" * 50)
    print(f"total_rows: {total_rows}")
    print(f"frap_rows: {frap_rows}")
    print(f"gappo_rows: {gappo_rows}")
    print(f"unknown_rows: {unknown_rows}")
    print(f"\nPrepared file: {OUTPUT_FILE.absolute()}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Prepare CSV for importing confirmed missing products"
    )
    parser.add_argument(
        "--input-file",
        required=True,
        help="Path to unmatched_exact_missing.csv",
    )
    args = parser.parse_args()

    input_file = Path(args.input_file)
    if not input_file.exists():
        print(f"Error: input file not found: {input_file}")
        sys.exit(1)

    try:
        skus = read_missing_skus(input_file)
    except ValueError as e:
        print(f"Error reading CSV: {e}")
        sys.exit(1)

    ensure_reports_dir()

    rows = build_rows(skus)
    write_csv(OUTPUT_FILE, rows)
    print_summary(rows)


if __name__ == "__main__":
    main()
