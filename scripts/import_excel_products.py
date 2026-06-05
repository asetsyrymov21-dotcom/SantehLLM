#!/usr/bin/env python3
"""Standalone script for importing products from Excel.

This is a manual entry point - not auto-connected to the main application.
Run directly: python scripts/import_excel_products.py path/to/file.xlsx
"""

import argparse
import json
import logging
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

# Bootstrap: add project root to path for standalone execution
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.services.product_import.excel_loader import ExcelLoader
from app.services.product_import.excel_mapper import (
    map_column_aliases,
    map_raw_row_to_excel_schema,
)
from app.services.product_import.excel_normalizer import normalize_excel_row
from app.services.product_import.merge_service import MergeService, _is_weak_title
from app.services.product_import.product_persistence_service import (
    persist_products,
    PersistenceSummary,
)
from app.db.session import SessionLocal

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


@dataclass
class DiagnosticEntry:
    """Diagnostic entry for a problematic row."""

    excel_row_index: int
    sku: str | None
    reason: str  # why flagged as problematic
    title_excel_header: str | None = None  # which Excel column is mapped to title
    raw_title_value: Any = None  # actual value from Excel title column
    raw_row: dict[str, Any] = field(default_factory=dict)
    mapped_row: dict[str, Any] | None = None
    normalized_row: dict[str, Any] | None = None
    unified_product: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        """Serialize to plain dict for JSON."""
        return {
            "excel_row_index": self.excel_row_index,
            "sku": self.sku,
            "reason": self.reason,
            "title_excel_header": self.title_excel_header,
            "raw_title_value": self.raw_title_value,
            "raw_row": self.raw_row,
            "mapped_row": self.mapped_row,
            "normalized_row": self.normalized_row,
            "unified_product": self.unified_product,
        }


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Import products from Excel file")
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
        "--mapping", type=str, default=None, help="Path to column mapping JSON file"
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Enable verbose logging"
    )
    parser.add_argument(
        "--debug-dir",
        type=str,
        default="debug",
        help="Directory for debug output (default: debug/)",
    )
    return parser.parse_args()


def load_excel(file_path: str, sheet: str | None, header_row: int) -> list[dict]:
    """Load rows from Excel file."""
    loader = ExcelLoader(file_path)
    return loader.load_excel_rows(sheet_name=sheet, header_row=header_row)


def map_rows_with_diag(
    raw_rows: list[dict],
    headers: list[str],
    source_file: str,
    source_sheet: str | None,
    diag_entries: list[DiagnosticEntry],
) -> list[dict]:
    """Map raw rows to standardized schema with diagnostic tracking."""
    column_mapping = map_column_aliases(headers)
    logger.info(f"Column mapping resolved: {column_mapping}")

    mapped_rows = []

    for idx, raw_row in enumerate(raw_rows):
        mapped = map_raw_row_to_excel_schema(
            raw_row=raw_row,
            column_mapping=column_mapping,
            source_file=source_file,
            source_sheet=source_sheet or "",
            source_row_index=idx,
        )
        if mapped is not None:
            mapped_rows.append((idx, raw_row, mapped))  # Keep index and raw for diag

    return mapped_rows, column_mapping


def normalize_rows_with_diag(
    mapped_rows_with_meta: list[tuple[int, dict, dict]],
) -> list[tuple[int, dict, dict, dict]]:
    """Normalize mapped rows with diagnostic tracking."""
    normalized = []
    for idx, raw_row, mapped_row in mapped_rows_with_meta:
        norm_row = normalize_excel_row(mapped_row)
        normalized.append((idx, raw_row, mapped_row, norm_row))
    return normalized


def build_products_with_diag(
    normalized_rows_with_meta: list[tuple[int, dict, dict, dict]],
    column_mapping: dict[str, str],
) -> tuple[list[dict], list[DiagnosticEntry]]:
    """Build unified products with diagnostic tracking for problematic rows."""
    service = MergeService()
    products = []
    diag_entries = []

    # Determine which Excel header maps to "title"
    title_excel_header = column_mapping.get("title")  # e.g., "Наименование"

    for idx, raw_row, mapped_row, norm_row in normalized_rows_with_meta:
        product = service.build_product_from_excel(norm_row)

        base_attrs = product.get("base_attributes") or {}
        products.append(product)

        # Check if problematic (needs enrichment or weak title)
        needs_enrichment = base_attrs.get("needs_pdf_enrichment", False)
        unified_title = product.get("title")
        mapped_title = mapped_row.get("title") if mapped_row else None

        if needs_enrichment or _is_weak_title(unified_title):
            # NEW CLASSIFICATION LOGIC: check specific title column, not any cell
            reason = "enrichment_flagged"  # default fallback

            # Check what was in the source Excel title column
            raw_title_value = None
            if title_excel_header and raw_row:
                raw_title_value = raw_row.get(title_excel_header)

            raw_title_str = (
                str(raw_title_value).strip() if raw_title_value is not None else ""
            )

            if title_excel_header is None:
                # No title column mapped at all
                reason = "title_column_not_mapped"
            elif raw_title_str == "":
                # Title column exists in Excel but is empty/null/whitespace
                reason = "title_empty_in_excel"
            elif mapped_title is None or str(mapped_title).strip() == "":
                # Raw has title, but mapper didn't capture it
                reason = "title_lost_in_mapper"
            elif _is_weak_title(unified_title):
                # Title present but weak (too short, just SKU, etc.)
                reason = "weak_title_after_normalize"

            diag_entries.append(
                DiagnosticEntry(
                    excel_row_index=idx,
                    sku=product.get("sku"),
                    reason=reason,
                    title_excel_header=title_excel_header,
                    raw_title_value=raw_title_value,
                    raw_row=dict(raw_row) if raw_row else {},
                    mapped_row=dict(mapped_row) if mapped_row else None,
                    normalized_row=dict(norm_row) if norm_row else None,
                    unified_product=dict(product) if product else None,
                )
            )

    return products, diag_entries


def save_debug_report(
    diag_entries: list[DiagnosticEntry],
    debug_dir: str,
    input_file: str,
) -> Path:
    """Save diagnostic report to JSON file."""
    debug_path = Path(debug_dir)
    debug_path.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"excel_diagnostic_{timestamp}.json"
    filepath = debug_path / filename

    report = {
        "generated_at": datetime.now().isoformat(),
        "input_file": input_file,
        "total_problematic_rows": len(diag_entries),
        "breakdown": {
            "title_lost_in_mapper": len(
                [e for e in diag_entries if e.reason == "title_lost_in_mapper"]
            ),
            "title_empty_in_excel": len(
                [e for e in diag_entries if e.reason == "title_empty_in_excel"]
            ),
            "weak_title_after_normalize": len(
                [e for e in diag_entries if e.reason == "weak_title_after_normalize"]
            ),
            "enrichment_flagged": len(
                [e for e in diag_entries if e.reason == "enrichment_flagged"]
            ),
        },
        "rows": [e.to_dict() for e in diag_entries],
    }

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2, default=str)

    return filepath


def print_import_summary(
    products: list[dict],
    diag_entries: list[DiagnosticEntry],
    dry_run: bool,
    summary: PersistenceSummary | None = None,
) -> None:
    """Print clear import policy summary with enrichment breakdown."""

    # Count enrichment needs from products (fallback if diag_entries empty)
    enriched_count = 0
    for p in products:
        attrs = p.get("base_attributes") or {}
        if attrs.get("needs_pdf_enrichment", False):
            enriched_count += 1

    print(f"\n{'='*50}")
    print(f"EXCEL IMPORT SUMMARY")
    print(f"{'='*50}")
    print(f"Total products built: {len(products)}")
    print(f"Products needing PDF enrichment: {enriched_count}")

    if diag_entries:
        # Calculate breakdown from diagnostics
        breakdown = {
            "title_empty_in_excel": len(
                [e for e in diag_entries if e.reason == "title_empty_in_excel"]
            ),
            "weak_title_after_normalize": len(
                [e for e in diag_entries if e.reason == "weak_title_after_normalize"]
            ),
            "title_lost_in_mapper": len(
                [e for e in diag_entries if e.reason == "title_lost_in_mapper"]
            ),
            "title_column_not_mapped": len(
                [e for e in diag_entries if e.reason == "title_column_not_mapped"]
            ),
            "enrichment_flagged": len(
                [e for e in diag_entries if e.reason == "enrichment_flagged"]
            ),
        }

        print(f"\nEnrichment breakdown:")
        for reason, count in breakdown.items():
            if count > 0:
                print(f"  - {reason}: {count}")

    print(f"\nImport policy:")
    print(f"  - Products are NOT skipped for missing/weak title")
    print(f"  - Such products are kept with needs_pdf_enrichment=true")
    print(f"  - Use PDF enrichment pipeline to fill missing titles later")

    if dry_run:
        print(f"\n[DRY RUN] No database changes were made")
    elif summary:
        print(f"\nPersistence results:")
        print(f"  - Inserted: {summary.inserted}")
        print(f"  - Updated: {summary.updated}")
        print(f"  - Failed: {summary.failed}")

    print(f"{'='*50}")


def save_products(products: list[dict], dry_run: bool) -> PersistenceSummary | None:
    """Save products to database.

    Args:
        products: List of built product dictionaries
        dry_run: If True, do not actually save

    Returns:
        PersistenceSummary or None if dry_run
    """
    if dry_run:
        logger.info(f"\n[DRY RUN] Would save {len(products)} products")

        # Count enrichment needs in dry run
        enriched_count = 0
        for p in products:
            attrs = p.get("base_attributes") or {}
            if attrs.get("needs_pdf_enrichment", False):
                enriched_count += 1

        logger.info(f"[DRY RUN] Products needing PDF enrichment: {enriched_count}")
        return None

    session = SessionLocal()
    try:
        summary = persist_products(session, products)
        session.commit()
        return summary
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def main() -> int:
    """Main entry point."""
    args = parse_args()

    # Set verbose logging if requested
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
        logging.getLogger("app.services.product_import").setLevel(logging.DEBUG)

    if not Path(args.file).exists():
        logger.error(f"Error: File not found: {args.file}")
        return 1

    logger.info(f"Starting import from: {args.file}")

    loader = ExcelLoader(args.file)
    sheet_names = loader.read_sheet_names()
    selected_sheet = (
        args.sheet if args.sheet else sheet_names[0] if sheet_names else None
    )

    logger.info(f"Using sheet: {selected_sheet}")

    raw_rows = load_excel(args.file, args.sheet, args.header_row)
    logger.info(f"Loaded {len(raw_rows)} raw rows from Excel")

    headers = list(raw_rows[0].keys()) if raw_rows else []
    logger.info(f"Detected headers: {headers}")

    # Stage 1: Map with diagnostic tracking
    mapped_with_meta, column_mapping = map_rows_with_diag(
        raw_rows, headers, args.file, selected_sheet, []
    )
    logger.info(
        f"Mapped to {len(mapped_with_meta)} product rows (filtered service rows)"
    )
    logger.info(f"Column mapping used: {column_mapping}")

    # Stage 2: Normalize
    normalized_with_meta = normalize_rows_with_diag(mapped_with_meta)

    # Stage 3: Build products + collect diagnostics
    products, diag_entries = build_products_with_diag(
        normalized_with_meta, column_mapping
    )
    logger.info(f"Built {len(products)} unified products")

    # Stage 4: Save diagnostic report
    if diag_entries:
        diag_path = save_debug_report(diag_entries, args.debug_dir, args.file)
        logger.info(f"[DIAGNOSTIC] Found {len(diag_entries)} problematic rows")
        logger.info(f"[DIAGNOSTIC] Debug report saved to: {diag_path}")

        # Print breakdown
        breakdown = {
            "title_lost_in_mapper": len(
                [e for e in diag_entries if e.reason == "title_lost_in_mapper"]
            ),
            "title_empty_in_excel": len(
                [e for e in diag_entries if e.reason == "title_empty_in_excel"]
            ),
            "weak_title_after_normalize": len(
                [e for e in diag_entries if e.reason == "weak_title_after_normalize"]
            ),
            "enrichment_flagged": len(
                [e for e in diag_entries if e.reason == "enrichment_flagged"]
            ),
        }
        for reason, count in breakdown.items():
            if count > 0:
                logger.info(f"[DIAGNOSTIC]  - {reason}: {count}")
    else:
        logger.info("[DIAGNOSTIC] No problematic rows found")

    if args.dry_run:
        logger.info("\n[DRY RUN] No database changes will be made")
        save_products(products, args.dry_run)
        print_import_summary(products, diag_entries, args.dry_run)
        return 0

    summary = save_products(products, args.dry_run)
    print_import_summary(products, diag_entries, args.dry_run, summary)

    return 0


if __name__ == "__main__":
    sys.exit(main())
