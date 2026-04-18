#!/usr/bin/env python3
"""
Audit missing products based on confirmed unmatched SKUs.

Reads unmatched_exact_missing.csv and prepares grouped CSV reports
to understand missing catalog coverage before importing new products.
"""

from __future__ import annotations

import argparse
import csv
import sys
from collections import Counter, defaultdict
from pathlib import Path


REPORTS_DIR = Path("reports/products_audit/missing_products_audit")


def ensure_reports_dir() -> None:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)


def write_csv(filepath: Path, fieldnames: list[str], rows: list[dict]) -> None:
    with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def get_expected_brand(sku: str) -> str:
    sku_upper = sku.strip().upper()
    if sku_upper.startswith("F"):
        return "FRAP"
    if sku_upper.startswith("G"):
        return "GAPPO"
    return "UNKNOWN"


def get_prefix(sku: str) -> str:
    sku = sku.strip()
    if not sku:
        return ""
    return sku[0].upper()


def get_sku_family(sku: str) -> str:
    sku = sku.strip().upper()
    if "-" in sku:
        return sku.split("-", 1)[0]
    return sku


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


def build_full_list_rows(skus: list[str]) -> list[dict]:
    rows: list[dict] = []
    for sku in skus:
        rows.append(
            {
                "source_sku": sku,
                "prefix": get_prefix(sku),
                "expected_brand": get_expected_brand(sku),
                "sku_family": get_sku_family(sku),
            }
        )
    return rows


def build_brand_summary(rows: list[dict]) -> list[dict]:
    counter = Counter(row["expected_brand"] for row in rows)
    ordered_brands = ["FRAP", "GAPPO", "UNKNOWN"]

    result: list[dict] = []
    for brand in ordered_brands:
        if brand in counter:
            result.append({"expected_brand": brand, "total": counter[brand]})

    for brand, total in sorted(counter.items()):
        if brand not in ordered_brands:
            result.append({"expected_brand": brand, "total": total})

    return result


def build_prefix_summary(rows: list[dict]) -> list[dict]:
    counter = Counter(row["prefix"] for row in rows)
    return [
        {"prefix": prefix, "total": total}
        for prefix, total in sorted(counter.items(), key=lambda x: (x[0],))
    ]


def build_family_summary(rows: list[dict]) -> list[dict]:
    family_counter: dict[tuple[str, str], int] = defaultdict(int)

    for row in rows:
        key = (row["sku_family"], row["expected_brand"])
        family_counter[key] += 1

    summary = [
        {
            "sku_family": sku_family,
            "expected_brand": expected_brand,
            "total": total,
        }
        for (sku_family, expected_brand), total in family_counter.items()
    ]

    summary.sort(key=lambda x: (-x["total"], x["sku_family"]))
    return summary


def print_summary(
    total_missing_rows: int,
    distinct_skus: int,
    brand_summary: list[dict],
    family_summary: list[dict],
) -> None:
    brand_map = {row["expected_brand"]: row["total"] for row in brand_summary}

    frap_missing = brand_map.get("FRAP", 0)
    gappo_missing = brand_map.get("GAPPO", 0)
    unknown_missing = brand_map.get("UNKNOWN", 0)

    distinct_families = len(family_summary)

    if family_summary:
        top_family = family_summary[0]["sku_family"]
        top_family_count = family_summary[0]["total"]
    else:
        top_family = ""
        top_family_count = 0

    print("\n" + "=" * 50)
    print("SUMMARY")
    print("=" * 50)
    print(f"total_missing_rows: {total_missing_rows}")
    print(f"distinct_skus: {distinct_skus}")
    print(f"frap_missing: {frap_missing}")
    print(f"gappo_missing: {gappo_missing}")
    print(f"unknown_missing: {unknown_missing}")
    print(f"distinct_families: {distinct_families}")
    print(f"top_family: {top_family}")
    print(f"top_family_count: {top_family_count}")
    print(f"\nReports saved to: {REPORTS_DIR.absolute()}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Audit confirmed missing products from unmatched SKUs"
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

    full_list_rows = build_full_list_rows(skus)
    brand_summary = build_brand_summary(full_list_rows)
    prefix_summary = build_prefix_summary(full_list_rows)
    family_summary = build_family_summary(full_list_rows)
    top_families = family_summary[:100]

    write_csv(
        REPORTS_DIR / "missing_products_full_list.csv",
        ["source_sku", "prefix", "expected_brand", "sku_family"],
        full_list_rows,
    )

    write_csv(
        REPORTS_DIR / "missing_products_by_brand.csv",
        ["expected_brand", "total"],
        brand_summary,
    )

    write_csv(
        REPORTS_DIR / "missing_products_prefix_summary.csv",
        ["prefix", "total"],
        prefix_summary,
    )

    write_csv(
        REPORTS_DIR / "missing_products_family_summary.csv",
        ["sku_family", "expected_brand", "total"],
        family_summary,
    )

    write_csv(
        REPORTS_DIR / "missing_products_top_families.csv",
        ["sku_family", "expected_brand", "total"],
        top_families,
    )

    print_summary(
        total_missing_rows=len(skus),
        distinct_skus=len(set(skus)),
        brand_summary=brand_summary,
        family_summary=family_summary,
    )


if __name__ == "__main__":
    main()
