#!/usr/bin/env python3
"""Import FRAP and GAPPO stock from Excel file.

Safe importer with dry-run by default.
Updates inventory for existing FRAP and GAPPO products.

Usage:
    python scripts/import_frap_stock.py --file "остатки.xlsx" --dry-run
    python scripts/import_frap_stock.py --file "остатки.xlsx" --commit
    python scripts/import_frap_stock.py --file "остатки.xlsx" --commit --report-dir ./reports
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

from app.db.session import SessionLocal
from app.services.stock_import import StockExcelParser, StockMatcher, StockImporter


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Import FRAP and GAPPO stock from Excel file"
    )
    parser.add_argument(
        "--file",
        "-f",
        type=str,
        required=True,
        help="Path to Excel file with stock data",
    )
    parser.add_argument(
        "--sheet",
        "-s",
        type=str,
        default=None,
        nargs="+",
        help="Sheet name(s) to read (default: 水 接)",
    )
    parser.add_argument(
        "--header-row",
        type=int,
        default=0,
        help="Header row index, 0-based (default: 0)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Show what would be changed without making changes (default)",
    )
    parser.add_argument(
        "--commit",
        action="store_true",
        help="Actually apply changes to database",
    )
    parser.add_argument(
        "--include-duplicates",
        action="store_true",
        help="Process duplicate SKUs (default: skip them)",
    )
    parser.add_argument(
        "--report-dir",
        type=str,
        default=None,
        help="Directory to save unmatched SKU report (default: no report)",
    )
    parser.add_argument(
        "--export-unmatched-csv",
        type=str,
        dest="unmatched_csv",
        default=None,
        metavar="PATH",
        help="Export unmatched SKUs to specific CSV file",
    )
    return parser.parse_args()


def export_unmatched_report(match_report, report_dir: Path, source_file: str) -> Path:
    """Export unmatched SKU report to CSV."""
    report_dir = Path(report_dir)
    report_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"unmatched_skus_{timestamp}.csv"
    filepath = report_dir / filename

    unmatched_report = match_report.get_unmatched_report()
    unmatched_report.to_csv_v2(filepath)

    return filepath


def log_import_start(
    file_path: str, sheets: str, mode: str, csv_path: str | None
) -> None:
    """Log import start information."""
    print("n" + "=" * 70)
    print("FRAP + GAPPO STOCK IMPORT - STARTING")
    print("=" * 70)
    print(f"[INPUT] Excel file: {Path(file_path).absolute()}")
    print(f"[INPUT] Sheets: {sheets}")
    print(f"[CONFIG] Mode: {mode}")
    if csv_path:
        print(f"[OUTPUT] Unmatched CSV: {Path(csv_path).absolute()}")
    print("=" * 70 + "n")


def log_unmatched_export(unmatched_report, csv_path: Path, rows_in_memory: int) -> None:
    """Log unmatched export information."""
    print("n" + "=" * 70)
    print("UNMATCHED SKU EXPORT REPORT")
    print("=" * 70)
    print(f"[MEMORY] Unmatched rows in memory: {rows_in_memory}")
    print(f"[OUTPUT] CSV file path: {csv_path.absolute()}")

    # Verify written rows
    import csv

    written_rows = 0
    try:
        with open(csv_path, "r", encoding="utf-8") as f:
            reader = csv.reader(f)
            next(reader)  # Skip header
            for _ in reader:
                written_rows += 1
    except Exception as e:
        print(f"[ERROR] Could not verify CSV: {e}")

    print(f"[VERIFY] Written rows to CSV: {written_rows}")
    if rows_in_memory == written_rows:
        print("[VERIFY] ✓ Row count matches!")
    else:
        print(f"[VERIFY] ✗ MISMATCH: memory={rows_in_memory}, written={written_rows}")
    print("=" * 70)


def main() -> int:
    args = parse_args()

    # Validate file
    file_path = Path(args.file)
    if not file_path.exists():
        print(f"Error: File not found: {args.file}", file=sys.stderr)
        return 1

    # Determine mode
    commit = args.commit
    dry_run = not commit

    # Sheet configuration
    sheet_arg = args.sheet  # None (default) or list of sheet names
    sheet_display = " ".join(sheet_arg) if sheet_arg else "default_sheets"

    # Determine output CSV path
    csv_path = None
    if args.unmatched_csv:
        csv_path = Path(args.unmatched_csv)
    elif args.report_dir:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        csv_path = Path(args.report_dir) / f"unmatched_skus_{timestamp}.csv"

    # Log start
    log_import_start(
        file_path=str(file_path),
        sheets=sheet_display,
        mode="COMMIT" if commit else "DRY-RUN",
        csv_path=str(csv_path) if csv_path else None,
    )

    print(f"File: {args.file}")
    print(f"Sheets: {sheet_display}")
    print(f"Mode: {'COMMIT' if commit else 'DRY-RUN'}")
    print()

    # Step 1: Parse Excel
    print("Step 1: Parsing Excel file...")
    try:
        parser = StockExcelParser(file_path, header_row=args.header_row)
        parse_result = parser.parse(sheet_name=sheet_arg)
        print(f"  Rows scanned: {parse_result.total_rows_scanned}")
        print(f"  Non-empty rows: {parse_result.non_empty_rows}")
        print()
    except Exception as e:
        print(f"Parse error: {e}", file=sys.stderr)
        return 1

    # Step 2: Match against database
    print("Step 2: Matching against database...")
    session = SessionLocal()
    try:
        matcher = StockMatcher(session, brand_filter=None)
        match_report = matcher.match_rows(parse_result.rows)

        # Set total rows scanned from parser
        match_report.total_rows_scanned = parse_result.total_rows_scanned

        print()

        # Step 3: Dry-run or Commit
        importer = StockImporter(
            session=session,
            source_file=str(file_path),
            source_name="frap_stock_excel",
        )

        if dry_run:
            importer.dry_run(match_report)

            # Export unmatched report if requested
            if csv_path:
                print("n--- EXPORTING UNMATCHED REPORT ---")
                unmatched_report = match_report.get_unmatched_report()
                rows_in_memory = len(unmatched_report.unmatched_results)

                csv_path.parent.mkdir(parents=True, exist_ok=True)
                unmatched_report.to_csv_v2(csv_path)

                log_unmatched_export(unmatched_report, csv_path, rows_in_memory)

            print("n--- NO CHANGES MADE ---")
            print("Review the report above, then run with --commit to apply changes.")
            return 0

        # Commit mode
        print("Step 3: Committing changes...")
        commit_result = importer.commit(
            match_report,
            skip_duplicates=not args.include_duplicates,
        )

        # Final commit to database
        try:
            session.commit()
            commit_result.print_summary()

            # Export unmatched report if requested
            if csv_path and commit_result.skipped_no_product > 0:
                print("n--- EXPORTING UNMATCHED REPORT ---")
                unmatched_report = match_report.get_unmatched_report()
                rows_in_memory = len(unmatched_report.unmatched_results)

                csv_path.parent.mkdir(parents=True, exist_ok=True)
                unmatched_report.to_csv_v2(csv_path)

                log_unmatched_export(unmatched_report, csv_path, rows_in_memory)

            print("nChanges committed successfully.")
            return 0
        except Exception as e:
            session.rollback()
            print(f"nCOMMIT FAILED: {e}", file=sys.stderr)
            return 1

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    finally:
        session.close()


if __name__ == "__main__":
    sys.exit(main())
