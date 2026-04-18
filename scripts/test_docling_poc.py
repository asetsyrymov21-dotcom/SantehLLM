#!/usr/bin/env python3
"""
Proof of concept CLI for testing Docling PDF extraction.

Tests both table and gallery page types from catalog PDFs.

Usage:
    # Test table page
    python scripts/test_docling_poc.py --pdf "2026 FRAP.pdf" --page 20 --type table
    
    # Test gallery page  
    python scripts/test_docling_poc.py --pdf "2026 FRAP.pdf" --page 50 --type gallery
    
    # Auto-detect page type
    python scripts/test_docling_poc.py --pdf "2026 FRAP.pdf" --page 20
    
    # Save to JSON
    python scripts/test_docling_poc.py --pdf "2026 FRAP.pdf" --page 20 --output result.json
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def check_docling():
    """Check if Docling is installed."""
    try:
        from app.services.pdf.docling import DoclingExtractor
        return True
    except ImportError as e:
        print(f"\n❌ Error: {e}")
        print("\nTo install Docling, run:")
        print("  pip install -r requirements-docling.txt")
        print("\nOr manually:")
        print("  pip install docling>=2.0.0")
        return False


def print_table_result(result):
    """Pretty print table extraction result."""
    print(f"\n📋 TABLE PAGE {result.page_number}")
    print("=" * 60)
    print(f"Title: {result.title or '(not found)'}")
    print(f"Brand: {result.brand_hint or '(none)'}")
    print(f"Rows found: {len(result.table_rows)}")
    
    if result.table_headers:
        print(f"\nHeaders: {', '.join(result.table_headers[:5])}...")
    
    if result.table_rows:
        print("\nFirst 3 rows:")
        for i, row in enumerate(result.table_rows[:3], 1):
            print(f"  {i}. SKU: {row.sku or 'N/A'}")
            # Show key cells
            key_cells = {k: v for k, v in row.cells.items() 
                        if v and k not in ['артикул', 'sku', 'код']}
            for k, v in list(key_cells.items())[:3]:
                print(f"     {k}: {v}")
    else:
        print("\n⚠️  No table rows extracted")


def print_gallery_result(result):
    """Pretty print gallery extraction result."""
    print(f"\n🖼️  GALLERY PAGE {result.page_number}")
    print("=" * 60)
    print(f"Title: {result.title or '(not found)'}")
    print(f"Images found: {len(result.image_items)}")
    
    if result.image_items:
        print("\nFirst 3 images:")
        for i, item in enumerate(result.image_items[:3], 1):
            print(f"  {i}. Image #{item.image_index}")
            print(f"     SKU: {item.sku or '(not extracted)'}")
            caption = item.caption[:80] if item.caption else "(no caption)"
            print(f"     Caption: {caption}...")
    else:
        print("\n⚠️  No images found")


def print_other_result(result):
    """Print result for non-table/gallery pages."""
    print(f"\n📄 PAGE {result.page_number} - Type: {result.page_type.value.upper()}")
    print("=" * 60)
    print(f"Title: {result.title or '(not found)'}")
    
    if result.raw_text:
        preview = result.raw_text[:300].replace('\n', ' ')
        print(f"\nText preview:\n  {preview}...")
    
    if result.docling_items:
        print(f"\nDocling items found: {', '.join(result.docling_items)}")


def save_to_json(result, output_path):
    """Save result to JSON file."""
    data = {
        "page_number": result.page_number,
        "page_type": result.page_type.value,
        "title": result.title,
        "brand_hint": result.brand_hint,
        "has_products": result.has_products(),
        "processing_time_ms": result.processing_time_ms,
    }
    
    if result.page_type.value == "table":
        data["table"] = {
            "headers": result.table_headers,
            "row_count": len(result.table_rows),
            "rows": [
                {
                    "sku": r.sku,
                    "cells": r.cells,
                }
                for r in result.table_rows
            ]
        }
    elif result.page_type.value == "gallery":
        data["gallery"] = {
            "image_count": len(result.image_items),
            "items": [
                {
                    "index": i.image_index,
                    "sku": i.sku,
                    "caption": i.caption,
                }
                for i in result.image_items
            ]
        }
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    print(f"\n💾 Saved to: {output_path}")


def main():
    parser = argparse.ArgumentParser(
        description='Test Docling PDF extraction (Proof of Concept)',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Quick test on page 20
  python %(prog)s --pdf "2026 FRAP.pdf" --page 20
  
  # Save result to JSON
  python %(prog)s --pdf "2026 FRAP.pdf" --page 20 --output result.json
  
  # Verbose logging
  python %(prog)s --pdf "2026 FRAP.pdf" --page 20 --verbose
        """
    )
    
    parser.add_argument(
        '--pdf', '-p',
        required=True,
        help='Path to PDF file'
    )
    parser.add_argument(
        '--page', '-P',
        type=int,
        required=True,
        help='Page number to test (1-based)'
    )
    parser.add_argument(
        '--brand', '-b',
        default=None,
        help='Brand hint (e.g., FRAP, GAPPO)'
    )
    parser.add_argument(
        '--output', '-o',
        default=None,
        help='Save result to JSON file'
    )
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable debug logging'
    )
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    # Check Docling available
    if not check_docling():
        sys.exit(1)
    
    from app.services.pdf.docling import DoclingExtractor
    
    pdf_path = Path(args.pdf)
    if not pdf_path.exists():
        print(f"❌ PDF not found: {pdf_path}")
        sys.exit(1)
    
    print(f"\n🔍 Testing Docling extraction")
    print(f"File: {pdf_path.name}")
    print(f"Page: {args.page}")
    print(f"Brand: {args.brand or '(auto)'}")
    print("-" * 60)
    
    # Extract
    try:
        extractor = DoclingExtractor()
        result = extractor.extract_page(
            pdf_path=pdf_path,
            page_number=args.page,
            brand_hint=args.brand,
        )
    except Exception as e:
        logger.exception("Extraction failed")
        print(f"\n❌ Extraction failed: {e}")
        sys.exit(1)
    
    # Print result based on type
    if result.page_type.value == "table":
        print_table_result(result)
    elif result.page_type.value == "gallery":
        print_gallery_result(result)
    else:
        print_other_result(result)
    
    # Summary
    print(f"\n{'=' * 60}")
    print(f"Page type detected: {result.page_type.value.upper()}")
    print(f"Has products: {'✅ Yes' if result.has_products() else '❌ No'}")
    print(f"Processing time: {result.processing_time_ms:.0f}ms")
    
    # Save to JSON if requested
    if args.output:
        save_to_json(result, args.output)
    
    print("\n✅ Done!\n")


if __name__ == '__main__':
    main()
