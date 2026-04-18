#!/usr/bin/env python3
"""
CLI tool for importing products from PDF extraction.

Safe workflow: dry-run first, then commit.

Usage:
    # Dry run (recommended first step)
    python scripts/import_extracted_products.py \\
        --pdf "/tmp/2026 FRAP.pdf" \\
        --brand FRAP \\
        --pages 10-20 \\
        --dry-run

    # Commit to database
    python scripts/import_extracted_products.py \\
        --pdf "/tmp/2026 FRAP.pdf" \\
        --brand FRAP \\
        --pages 10-20 \\
        --commit
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from app.db.session import SessionLocal
from app.services.product_import import ProductImporter, ImportResult
from app.services.pdf import inspect_pdf, detect_page_type, extract_text_from_page
from app.services.pdf.extractor import extract_catalog_grids_from_page
from app.services.pdf.product_cards import extract_product_cards_from_page

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def parse_page_range(pages_str: str) -> list[int]:
    """Parse '10-20' or '5' into list of page numbers."""
    pages_str = pages_str.strip()

    if "-" in pages_str:
        start, end = pages_str.split("-", 1)
        return list(range(int(start), int(end) + 1))
    return [int(pages_str)]


def extract_products_from_pages(
    pdf_path: Path, page_numbers: list[int], brand_hint: str | None
) -> list[dict]:
    """Extract and flatten products from PDF pages."""

    all_items = []

    for page_num in page_numbers:
        logger.info(f"Processing page {page_num}.")

        try:
            text = extract_text_from_page(pdf_path, page_num)
            page_type = detect_page_type(text, page_number=page_num)

            logger.info(f"Page {page_num}: detected page_type={page_type}")

            if page_type == "marketing":
                logger.info(f"Page {page_num}: skip marketing page")
                continue

            if page_type == "grid_catalog":
                blocks = extract_catalog_grids_from_page(pdf_path, page_num, brand_hint)
            elif page_type == "product_cards":
                blocks = extract_product_cards_from_page(pdf_path, page_num, brand_hint)
            else:
                blocks = extract_catalog_grids_from_page(pdf_path, page_num, brand_hint)
                if not blocks:
                    blocks = extract_product_cards_from_page(
                        pdf_path, page_num, brand_hint
                    )

            if not blocks:
                logger.warning(
                    f"Page {page_num}: no product blocks found after type-specific extraction"
                )
                continue

            for block in blocks:
                logger.info(
                    f"Page {page_num}: '{block.title}' with {len(block.rows)} rows"
                )

                for row in block.rows:
                    item = {
                        "sku": row.get("sku") or row.get("артикул"),
                        "name": f"{block.title} {row.get('size', '')}".strip(),
                        "brand": getattr(block, "brand", None),
                        "category": getattr(block, "category", None)
                        or detect_category(block.title),
                        "description": getattr(block, "subtitle", None),
                        "attributes": row,
                        "source_file": pdf_path.name,
                        "source_page": page_num,
                    }
                    all_items.append(item)

        except Exception as e:
            logger.error(f"Page {page_num} failed: {e}")
            continue

    return all_items


def detect_category(title: str) -> str | None:
    """Detect category from title heuristics."""
    title_lower = title.lower()

    categories = {
        "труб": "Трубы",
        "труба": "Трубы",
        "фитинг": "Фитинги",
        "смеситель": "Смесители",
        "кран": "Краны",
        "вентиль": "Вентили",
        "клапан": "Клапаны",
        "коллектор": "Коллекторы",
    }

    for keyword, cat in categories.items():
        if keyword in title_lower:
            return cat
    return None


def print_summary(
    pdf_info,
    page_numbers: list[int],
    raw_items: list[dict],
    import_result: ImportResult,
) -> None:
    """Print formatted summary."""

    print(f"\n{'='*60}")
    print("IMPORT SUMMARY")
    print(f"{'='*60}")

    print(f"\nPDF: {pdf_info.file_path}")
    print(f"  Pages: {pdf_info.page_count} total")
    print(f"  Size: {pdf_info.file_size_mb:.2f} MB")
    print(
        f"  Processed pages: {len(page_numbers)} ({min(page_numbers)}-{max(page_numbers)})"
    )

    print(f"\nExtraction:")
    print(f"  Raw rows extracted: {len(raw_items)}")

    print(f"\nImport Result:")
    print(f"  Mode: {'DRY RUN (no changes)' if import_result.dry_run else 'COMMIT'}")
    print(f"  Total unique: {import_result.total}")
    print(f"  Created: {import_result.created}")
    print(f"  Updated: {import_result.updated}")
    print(f"  Skipped: {import_result.skipped}")
    print(f"  Errors: {import_result.errors}")

    if import_result.details:
        skipped_items = [
            d for d in import_result.details if d.get("action") == "skipped"
        ]
        if skipped_items:
            print("\nSkipped details:")
            for d in skipped_items:
                print(
                    f"  page={d.get('page')} sku={d.get('sku')} "
                    f"reason={d.get('reason')} name={d.get('name')}"
                )

    suspicious_pages = getattr(import_result, "suspicious_pages", None)
    if suspicious_pages:
        printed_header = False

        for page in sorted(suspicious_pages.keys()):
            info = suspicious_pages[page]
            reasons = sorted(info.get("reasons", []))
            skus = sorted(info.get("skus", []))

            if not reasons:
                continue

            if not printed_header:
                print("\nSUSPICIOUS PAGES SUMMARY:")
                printed_header = True

            print(
                f"  page={page} "
                f"reasons={','.join(reasons)} "
                f"updated={info.get('updated', 0)} "
                f"created={info.get('created', 0)} "
                f"skipped={info.get('skipped', 0)} "
                f"skus={skus}"
            )

    changed_rows = getattr(import_result, "changed_rows", None)
    if changed_rows:
        review_rows = [
            row for row in changed_rows if row.get("action") in {"updated", "created"}
        ]

        if review_rows:
            print("\nCHANGED ROWS REVIEW:")
            for row in sorted(
                review_rows,
                key=lambda x: (
                    x.get("page") if x.get("page") is not None else 999999,
                    x.get("sku") or "",
                ),
            ):
                print(
                    f"  page={row.get('page')} "
                    f"sku={row.get('sku')} "
                    f"action={row.get('action')} "
                    f"issue_type={row.get('issue_type')} "
                    f"old_name={row.get('old_name')} "
                    f"new_name={row.get('new_name')}"
                )

        if import_result.dry_run and (
            import_result.created > 0 or import_result.updated > 0
        ):
            print(f"\n⚠️  To commit these changes, run with --commit")

    print(f"{'='*60}\n")


def main():
    parser = argparse.ArgumentParser(
        description="Import products from PDF catalog extraction",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Dry run first (safe)
  python %(prog)s --pdf "catalog.pdf" --brand FRAP --pages 10-20 --dry-run
  
  # Then commit
  python %(prog)s --pdf "catalog.pdf" --brand FRAP --pages 10-20 --commit
        """,
    )

    parser.add_argument("--pdf", "-p", required=True, help="Path to PDF file")
    parser.add_argument(
        "--brand", "-b", default=None, help="Brand hint (e.g., FRAP, GAPPO)"
    )
    parser.add_argument(
        "--pages", "-P", required=True, help='Page range, e.g., "10-20" or "5"'
    )

    mode_group = parser.add_mutually_exclusive_group(required=True)
    mode_group.add_argument(
        "--dry-run",
        "-n",
        action="store_true",
        help="Simulate import without database changes",
    )
    mode_group.add_argument(
        "--commit",
        "-c",
        action="store_true",
        help="Actually commit changes to database",
    )

    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose logging")

    args = parser.parse_args()

    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    pdf_path = Path(args.pdf)

    if not pdf_path.exists():
        print(f"ERROR: File not found: {pdf_path}", file=sys.stderr)
        sys.exit(1)

    # Inspect PDF
    try:
        pdf_info = inspect_pdf(pdf_path)
        logger.info(f"PDF: {pdf_info.page_count} pages, {pdf_info.file_size_mb:.2f} MB")
    except Exception as e:
        print(f"ERROR: Cannot read PDF: {e}", file=sys.stderr)
        sys.exit(1)

    # Parse page range
    try:
        page_numbers = parse_page_range(args.pages)
        invalid = [p for p in page_numbers if p < 1 or p > pdf_info.page_count]
        if invalid:
            raise ValueError(f"Invalid pages: {invalid}")
    except ValueError as e:
        print(f"ERROR: Invalid page range: {e}", file=sys.stderr)
        sys.exit(1)

    logger.info(
        f"Processing pages: {min(page_numbers)}-{max(page_numbers)} ({len(page_numbers)} pages)"
    )

    # Extract products
    raw_items = extract_products_from_pages(pdf_path, page_numbers, args.brand)

    if not raw_items:
        print("\nNo products extracted. Check PDF structure.\n")
        sys.exit(0)

    logger.info(f"Extracted {len(raw_items)} raw rows, starting import...")

    # Import to database
    db = SessionLocal()
    try:
        importer = ProductImporter(db)
        result = importer.import_products(items=raw_items, dry_run=not args.commit)
    finally:
        db.close()

    # Print summary
    print_summary(pdf_info, page_numbers, raw_items, result)

    # Exit code based on errors
    sys.exit(1 if result.errors > 0 else 0)


if __name__ == "__main__":
    main()
