#!/usr/bin/env python3
"""Standalone script for importing stock data from Excel.

Matches products by SKU, updates inventory table.
Duplicate rule: last row wins (processed in file order).
"""

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.db.session import SessionLocal
from app.services.product_import.excel_loader import ExcelLoader
from app.services.product_import.stock_import_service import StockImportService


@dataclass
class StockImportSummary:
    total_received: int
    matched: int
    upserted: int
    unmatched: int
    skipped: int
    failed: int


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import stock data from Excel")
    parser.add_argument("file", type=str, help="Path to Excel file")
    parser.add_argument(
        "--sheet", type=str, default=None, help="Sheet name (default: first sheet)"
    )
    parser.add_argument(
        "--header-row", type=int, default=0, help="Header row index (default: 0)"
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="Do not save to database"
    )
    parser.add_argument(
        "--debug-preview",
        action="store_true",
        help="Show diagnostic preview of first 5 rows",
    )
    return parser.parse_args()


def load_excel_rows(file_path: str, sheet: str | None, header_row: int) -> list[dict]:
    loader = ExcelLoader(file_path)
    return loader.load_excel_rows(sheet_name=sheet, header_row=header_row)


def _get_row_value_case_insensitive(
    row: dict[str, Any], candidates: list[str]
) -> Any | None:
    lowered = {str(k).strip().lower(): v for k, v in row.items()}
    for key in candidates:
        if key.lower() in lowered:
            return lowered[key.lower()]
    return None


def trim_stock_rows(rows: list[dict], break_streak: int = 50) -> list[dict]:
    trimmed: list[dict] = []
    empty_sku_streak = 0

    for row in rows:
        sku = _extract_sku(row)

        if sku:
            trimmed.append(row)
            empty_sku_streak = 0
        else:
            empty_sku_streak += 1
            if empty_sku_streak >= break_streak:
                break

    return trimmed


def _extract_sku(row: dict[str, Any]) -> str | None:
    value = _get_row_value_case_insensitive(
        row, ["sku", "артикул", "арт.", "код", "code"]
    )
    if value is None:
        return None

    s = str(value).strip()
    if s and s.lower() not in ("none", "nan", ""):
        return s
    return None


def _normalize_qty(value: Any) -> float | None:
    """Duplicate of StockImportService._normalize_qty for preview."""
    if isinstance(value, (int, float)):
        return float(value) if float(value) >= 0 else None
    if isinstance(value, str):
        cleaned = value.replace(" ", "").replace("\xa0", "").replace(",", ".")
        try:
            qty = float(cleaned)
            return qty if qty >= 0 else None
        except ValueError:
            pass
    return None


def _extract_quantity(row: dict[str, Any]) -> float | None:
    value = _get_row_value_case_insensitive(
        row, ["quantity", "количество", "остаток", "qty", "stock", "наличие", "1с"]
    )
    if value is not None:
        return _normalize_qty(value)
    return None


def debug_preview(rows: list[dict]) -> None:
    """Print diagnostic preview of first 5 rows."""
    if not rows:
        print("No rows to preview")
        return

    print("\n=== DEBUG PREVIEW ===")

    # Detected headers
    print(f"\n--- Detected Headers ({len(rows[0])} columns) ---")
    for i, h in enumerate(rows[0].keys(), 1):
        print(f"  {i}. '{h}'")

    # First 5 raw rows
    preview_count = min(5, len(rows))
    print(f"\n--- First {preview_count} Raw Rows ---")
    for i, row in enumerate(rows[:preview_count], 1):
        print(f"  Row {i}: {dict(row)}")

    # First 5 mapped rows (extraction results)
    print(f"\n--- First {preview_count} Mapped Rows (SKU/Qty extraction) ---")
    for i, row in enumerate(rows[:preview_count], 1):
        raw_sku = None
        raw_qty = None
        # Show which keys matched
        for key in ["sku", "артикул", "арт.", "код", "code"]:
            if key in row and row[key] is not None:
                raw_sku = (key, row[key])
                break
        for key in [
            "quantity",
            "количество",
            "остаток",
            "qty",
            "stock",
            "наличие",
            "1c",
        ]:
            if key in row and row[key] is not None:
                raw_qty = (key, row[key])
                break
        print(f"  Row {i}: SKU src={raw_sku}, Qty src={raw_qty}")

    # First 5 normalized rows (final extraction)
    print(f"\n--- First {preview_count} Normalized Rows ---")
    for i, row in enumerate(rows[:preview_count], 1):
        sku = _extract_sku(row)
        qty = _extract_quantity(row)
        status = "OK" if sku and qty is not None else "SKIP"
        print(f"  Row {i}: status={status}, sku='{sku}', qty={qty}")

    print("\n=== END PREVIEW ===\n")


def main() -> int:
    args = parse_args()

    if not Path(args.file).exists():
        print(f"Error: File not found: {args.file}", file=sys.stderr)
        return 1

    rows = load_excel_rows(args.file, args.sheet, args.header_row)
    rows = trim_stock_rows(rows)

    if not rows:
        print("No data rows found in Excel")
        return 0

    if args.debug_preview:
        debug_preview(rows)
        return 0

    if args.dry_run:
        print(f"DRY RUN: Would process {len(rows)} stock rows")
        return 0

    session = SessionLocal()
    try:
        service = StockImportService(session)
        result = service.import_stock_rows(rows)
        session.commit()

        print("\n=== Stock Import Summary ===")
        print(f"Total received: {result.total_received}")
        print(f"Matched: {result.matched}")
        print(f"Upserted: {result.upserted}")
        print(f"Unmatched: {result.unmatched}")
        print(f"Skipped: {result.skipped}")
        print(f"Failed: {result.failed}")
        print("===========================")

        return 0 if result.failed == 0 else 1

    except Exception as e:
        session.rollback()
        print(f"Import failed: {e}", file=sys.stderr)
        return 1
    finally:
        session.close()


if __name__ == "__main__":
    sys.exit(main())
