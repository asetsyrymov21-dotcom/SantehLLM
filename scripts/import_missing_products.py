#!/usr/bin/env python3
"""
Import confirmed-missing products into products table.

Input:
- reports/products_audit/missing_products_audit/prepare_missing_products_import.csv

Behavior:
- dry-run by default
- real insert only with --commit
- inserts only SKUs that do not already exist
- does not update existing products
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

from app.db.models import Product
from app.db.session import SessionLocal


def read_rows(input_file: Path) -> list[dict]:
    with open(input_file, "r", newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)

        if not reader.fieldnames:
            raise ValueError("CSV file is empty or has no headers")

        required = {"sku", "brand", "name", "source", "needs_name_fill"}
        missing = required - set(reader.fieldnames)
        if missing:
            raise ValueError(
                f"Missing required columns: {sorted(missing)}. "
                f"Found: {reader.fieldnames}"
            )

        rows: list[dict] = []
        for row in reader:
            sku = (row.get("sku") or "").strip()
            brand = (row.get("brand") or "").strip().upper()
            name = (row.get("name") or "").strip()
            source = (row.get("source") or "").strip()
            needs_name_fill = str(row.get("needs_name_fill") or "").strip()

            if not sku:
                continue

            rows.append(
                {
                    "sku": sku,
                    "brand": brand,
                    "name": name,
                    "source": source,
                    "needs_name_fill": needs_name_fill,
                }
            )

    return rows


def load_existing_skus(session) -> set[str]:
    rows = session.query(Product.sku).all()
    return {sku for (sku,) in rows if sku}


def build_placeholder_name(sku: str, brand: str) -> str:
    return f"{brand} {sku}"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Import confirmed missing products into catalog"
    )
    parser.add_argument(
        "--input-file",
        required=True,
        help="Path to prepare_missing_products_import.csv",
    )
    parser.add_argument(
        "--commit",
        action="store_true",
        help="Actually insert rows into DB",
    )
    args = parser.parse_args()

    input_file = Path(args.input_file)
    if not input_file.exists():
        print(f"Error: input file not found: {input_file}")
        sys.exit(1)

    try:
        rows = read_rows(input_file)
    except ValueError as e:
        print(f"Error reading CSV: {e}")
        sys.exit(1)

    session = SessionLocal()
    try:
        existing_skus = load_existing_skus(session)

        scanned = 0
        already_exists = 0
        to_create = 0
        created = 0
        skipped_unknown_brand = 0
        skipped_duplicate_in_input = 0

        seen_input_skus: set[str] = set()
        pending_objects: list[Product] = []

        for row in rows:
            scanned += 1

            sku = row["sku"]
            brand = row["brand"]
            name = row["name"]

            if sku in seen_input_skus:
                skipped_duplicate_in_input += 1
                continue
            seen_input_skus.add(sku)

            if brand not in {"FRAP", "GAPPO"}:
                skipped_unknown_brand += 1
                continue

            if sku in existing_skus:
                already_exists += 1
                continue

            to_create += 1

            product = Product(
                sku=sku,
                brand=brand,
                name=name or build_placeholder_name(sku, brand),
            )
            pending_objects.append(product)

        if args.commit and pending_objects:
            session.add_all(pending_objects)
            session.commit()
            created = len(pending_objects)
        elif args.commit:
            session.commit()

        print("\n" + "=" * 50)
        print("SUMMARY")
        print("=" * 50)
        print(f"scanned: {scanned}")
        print(f"already_exists: {already_exists}")
        print(f"to_create: {to_create}")
        print(f"created: {created}")
        print(f"skipped_unknown_brand: {skipped_unknown_brand}")
        print(f"skipped_duplicate_in_input: {skipped_duplicate_in_input}")
        print(f"mode: {'commit' if args.commit else 'dry-run'}")

    except Exception:
        if args.commit:
            session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    main()
