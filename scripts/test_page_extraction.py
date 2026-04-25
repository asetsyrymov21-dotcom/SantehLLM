"""
Test script for PDF page extraction with type detection.

Usage:
    python scripts/test_page_extraction.py <pdf_path> <page_number>

Example:
    python scripts/test_page_extraction.py "2026 GAPPO.pdf" 5
    python scripts/test_page_extraction.py "2026 FRAP.pdf" 10

This script:
1. Inspects the page type (grid_catalog, product_cards, marketing, unknown)
2. Shows a sample of extracted text
3. Extracts and displays product blocks
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.services.pdf import (
    inspect_page,
    extract_page_products,
    detect_page_type,
    extract_text_from_page,
    is_valid_sku,
)
from app.services.pdf.extractor import extract_catalog_grids_from_page
from app.services.pdf.product_cards import extract_product_cards_from_page

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def print_header(text: str) -> None:
    """Print formatted header."""
    print("\n" + "=" * 60)
    print(text)
    print("=" * 60)


def print_subheader(text: str) -> None:
    """Print formatted subheader."""
    print("\n" + "-" * 40)
    print(text)
    print("-" * 40)


def test_page(pdf_path: Path, page_number: int, brand_hint: str | None = None) -> None:
    """Run full page extraction test."""

    print_header(f"Testing: {pdf_path.name} - Page {page_number}")

    # Step 1: Inspect page
    print_subheader("Step 1: Page Inspection")
    try:
        info = inspect_page(pdf_path, page_number)
        print(f"  Page Type:    {info['page_type']}")
        print(f"  Text Length:  {info['text_length']} chars")
        print(f"  Line Count:   {info['line_count']}")
        print(f"  SKU Count:    {info['sku_count']}")
    except Exception as e:
        print(f"  ERROR: {e}")
        return

    # Step 2: Show text sample
    print_subheader("Step 2: Text Sample (first 800 chars)")
    text = extract_text_from_page(pdf_path, page_number)
    sample = text[:800] + "..." if len(text) > 800 else text
    # Format for display
    lines = sample.split("\n")
    for i, line in enumerate(lines[:30], 1):  # Show first 30 lines
        if line.strip():
            print(f"  {i:2d}: {line[:80]}")
    if len(lines) > 30:
        print(f"  ... ({len(lines) - 30} more lines)")

    # Step 3: Type-specific extraction
    print_subheader("Step 3: Type-Specific Extraction")
    page_type = info["page_type"]

    if page_type == "grid_catalog":
        print("  Using: extract_catalog_grids_from_page()")
        blocks = extract_catalog_grids_from_page(pdf_path, page_number, brand_hint)
    elif page_type == "product_cards":
        print("  Using: extract_product_cards_from_page()")
        blocks = extract_product_cards_from_page(pdf_path, page_number, brand_hint)
    elif page_type == "marketing":
        print("  Page type: marketing - no products to extract")
        blocks = []
    else:
        print("  Page type: unknown - trying generic extraction")
        # Try both extractors as fallback
        blocks = extract_catalog_grids_from_page(pdf_path, page_number, brand_hint)
        if not blocks:
            blocks = extract_product_cards_from_page(pdf_path, page_number, brand_hint)

    # Step 4: Display results
    print_subheader("Step 4: Extraction Results")
    print(f"  Found {len(blocks)} product blocks")

    for i, block in enumerate(blocks, 1):
        print(f"\n  Block #{i}:")
        print(
            f"    Title:    {block.title[:60]}"
            + ("..." if len(block.title) > 60 else "")
        )
        print(
            f"    Subtitle: {block.subtitle[:50]}"
            if block.subtitle
            else "    Subtitle: (none)"
        )
        print(f"    Brand:    {block.brand}")
        print(f"    Rows:     {len(block.rows)} variants")

        # Show first few SKUs
        skus = [row.get("sku", "N/A") for row in block.rows[:5]]
        print(f"    SKUs:     {', '.join(skus)}")
        if len(block.rows) > 5:
            print(f"             ... and {len(block.rows) - 5} more")


def test_page_type_only(pdf_path: Path, page_number: int) -> None:
    """Quick test to just detect page type."""
    text = extract_text_from_page(pdf_path, page_number)
    page_type = detect_page_type(text, page_number=page_number)
    print(f"Page {page_number}: {page_type}")


def batch_test(pdf_path: Path, start_page: int, end_page: int) -> None:
    """Test multiple pages to see type distribution."""
    print_header(f"Batch Testing: {pdf_path.name} (pages {start_page}-{end_page})")

    types = {"grid_catalog": 0, "product_cards": 0, "marketing": 0, "unknown": 0}

    for page_num in range(start_page, end_page + 1):
        try:
            text = extract_text_from_page(pdf_path, page_num)
            page_type = detect_page_type(text, page_number=page_num)

            if page_num in [53, 54, 55, 56, 57]:
                print(f"DEBUG PAGE {page_num}: {page_type}")

            types[page_type] = types.get(page_type, 0) + 1
            print(f"  Page {page_num:3d}: {page_type}")
        except Exception as e:
            print(f"  Page {page_num:3d}: ERROR - {e}")

    print_subheader("Summary")
    for t, count in types.items():
        print(f"  {t:15s}: {count} pages")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Test PDF page extraction with type detection"
    )
    parser.add_argument("pdf_path", help="Path to PDF file")
    parser.add_argument("page_number", type=int, help="Page number to test (1-based)")
    parser.add_argument("--brand", "-b", help="Brand hint (e.g., GAPPO, FRAP)")
    parser.add_argument(
        "--batch", "-B", action="store_true", help="Batch mode: test range of pages"
    )
    parser.add_argument("--end-page", "-e", type=int, help="End page for batch mode")
    parser.add_argument(
        "--type-only", "-t", action="store_true", help="Only show page type"
    )

    args = parser.parse_args()

    pdf_path = Path(args.pdf_path)
    if not pdf_path.exists():
        print(f"Error: File not found: {pdf_path}")
        return 1

    if args.batch:
        end_page = args.end_page or args.page_number + 10
        batch_test(pdf_path, args.page_number, end_page)
    elif args.type_only:
        test_page_type_only(pdf_path, args.page_number)
    else:
        test_page(pdf_path, args.page_number, args.brand)

    return 0


if __name__ == "__main__":
    sys.exit(main())
