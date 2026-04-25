#!/usr/bin/env python3
"""
Script for testing product extraction from PDF pages.

Reads full_audit.txt with classifier results, selects test samples,
runs extraction through router, and saves results for analysis.

Usage:
    python scripts/test_extraction_audit.py

Output:
    extraction_audit.jsonl - One JSON line per tested page
"""

from __future__ import annotations

import json
import logging
import random
import re
from collections import defaultdict
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# Add project root to path
import sys

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Project imports
from app.services.pdf.router import extract_page_products, extract_text_from_page
from app.services.pdf.classifier import detect_page_type
from app.schemas.product_extraction import (
    ExtractedProduct,
    ExtractionAuditRecord,
    ExtractionAuditSummary,
)

if TYPE_CHECKING:
    from app.services.pdf.extractor import ProductBlock


# =============================================================================
# Constants
# =============================================================================

AUDIT_FILE = Path("full_audit.txt")
OUTPUT_FILE = Path("extraction_audit.jsonl")

SAMPLE_CONFIG = {
    "product_cards": 10,
    "grid_catalog": 5,
    "unknown": 5,
}

PDF_FILENAME = "2026 GAPPOсмесители каталог .pdf"


# =============================================================================
# Audit Parser
# =============================================================================


def parse_audit_file(audit_path: Path) -> dict[str, list[int]]:
    """Parse full_audit.txt and group pages by type.

    Returns:
        Dictionary mapping page_type -> list of page numbers
    """
    pages_by_type: dict[str, list[int]] = defaultdict(list)

    if not audit_path.exists():
        logger.error("Audit file not found: %s", audit_path)
        return dict(pages_by_type)

    text = audit_path.read_text(encoding="utf-8", errors="ignore")

    # Pattern: "Page 123: product_cards" or "Page 123: grid_catalog"
    # Also handles "Page 123: marketing" and "Page 123: unknown"
    page_pattern = re.compile(
        r"Page\s+(\d+)\s*:\s*(product_cards|grid_catalog|marketing|unknown)",
        re.IGNORECASE,
    )

    for match in page_pattern.finditer(text):
        page_num = int(match.group(1))
        page_type = match.group(2).lower()
        pages_by_type[page_type].append(page_num)

    logger.info("Parsed audit file:")
    for page_type, pages in sorted(pages_by_type.items()):
        logger.info("  %s: %d pages", page_type, len(pages))

    return dict(pages_by_type)


def select_test_sample(
    pages_by_type: dict[str, list[int]], config: dict[str, int]
) -> list[tuple[int, str]]:
    """Select random sample of pages for testing.

    Args:
        pages_by_type: Pages grouped by type
        config: Desired sample size per type

    Returns:
        List of (page_number, page_type) tuples
    """
    selected: list[tuple[int, str]] = []
    random.seed(42)  # Reproducible samples

    for page_type, desired_count in config.items():
        available = pages_by_type.get(page_type, [])

        if not available:
            logger.warning("No pages of type '%s' found in audit", page_type)
            continue

        # Select random sample or all available if less than desired
        sample_size = min(desired_count, len(available))
        sample = random.sample(available, sample_size)

        logger.info(
            "Selected %d/%d pages of type '%s'", sample_size, len(available), page_type
        )

        for page_num in sample:
            selected.append((page_num, page_type))

    # Sort by page number for consistent processing order
    selected.sort(key=lambda x: x[0])

    return selected


# =============================================================================
# Product Extraction
# =============================================================================


def convert_blocks_to_products(blocks: list[ProductBlock]) -> list[ExtractedProduct]:
    """Convert ProductBlock objects to ExtractedProduct schema.

    Args:
        blocks: List of ProductBlock from extractor

    Returns:
        List of ExtractedProduct with individual products
    """
    products: list[ExtractedProduct] = []

    for block in blocks:
        # Each block has a title and rows (variants)
        base_name = block.title or ""
        brand = block.brand

        for row in block.rows:
            sku = row.get("sku") or row.get("артикул")

            # Build product name from block title and row data
            name_parts = [base_name]
            if row.get("size"):
                name_parts.append(f"Size: {row['size']}")

            name = " ".join(filter(None, name_parts))

            # Try to extract price if available
            price = None
            for price_key in ["price", "цена", "стоимость"]:
                if price_key in row and row[price_key]:
                    try:
                        price_str = (
                            str(row[price_key]).replace(" ", "").replace(",", ".")
                        )
                        price = float(price_str)
                        break
                    except (ValueError, TypeError):
                        pass

            product = ExtractedProduct(
                sku=sku,
                name=name if name else None,
                price=price,
                brand=brand,
                confidence=1.0,  # Our extractor doesn't provide confidence yet
            )
            products.append(product)

    return products


def extract_single_detail_product(
    pdf_path: Path,
    page_number: int,
    brand_hint: Optional[str] = None,
) -> list[ExtractedProduct]:
    """Fallback extractor for single-product detail pages.

    Looks for:
    - one main SKU like GR1053
    - nearby product title / description
    - optional technical attributes (Цвет, Материал, etc.)

    Returns:
        List with one ExtractedProduct if detected, otherwise empty list.
    """
    try:
        text = extract_text_from_page(pdf_path=pdf_path, page_number=page_number)
    except Exception:
        return []

    if not text:
        return []

    # Normalize text
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    full_text = "\n".join(lines)

    # SKU pattern like GR1053, G31002-3, G52-4L
    sku_pattern = re.compile(r"\b([A-ZА-Я]{1,3}\d{2,5}(?:-\d+[A-ZА-Я]?)?)\b")
    sku_matches = sku_pattern.findall(full_text)

    if not sku_matches:
        return []

    # Prefer first SKU on page as primary
    sku = sku_matches[0]

    # Heuristic signals for detail page
    detail_markers = [
        "Цвет:",
        "Материал:",
        "Температура:",
        "Напряжение",
        "Степень защиты",
    ]
    has_detail_markers = any(marker in full_text for marker in detail_markers)

    if not has_detail_markers:
        return []

    # Try to extract name:
    # often name is the first non-SKU text line after the SKU line
    name = None
    for i, line in enumerate(lines):
        if sku in line:
            # next 1-2 non-empty lines may contain the name
            candidate_lines = []
            for j in range(i + 1, min(i + 4, len(lines))):
                candidate = lines[j]
                if any(marker in candidate for marker in detail_markers):
                    break
                if len(candidate) > 2:
                    candidate_lines.append(candidate)
            if candidate_lines:
                name = " ".join(candidate_lines).strip()
            break

    # Fallback: if no name found, use a generic placeholder from nearby text
    if not name:
        for line in lines:
            if line != sku and not any(marker in line for marker in detail_markers):
                if len(line) > 5 and not sku_pattern.search(line):
                    name = line
                    break

    product = ExtractedProduct(
        sku=sku,
        name=name,
        price=None,
        brand=brand_hint,
        confidence=0.85,
    )

    return [product]


def extract_from_page(
    pdf_path: Path,
    page_number: int,
    expected_type: str,
    brand_hint: Optional[str] = None,
) -> ExtractionAuditRecord:
    """Extract products from a single PDF page.

    Args:
        pdf_path: Path to PDF file
        page_number: 1-based page number
        expected_type: Expected page type from audit
        brand_hint: Optional brand hint

    Returns:
        ExtractionAuditRecord with results
    """
    record = ExtractionAuditRecord(
        page=page_number,
        page_type=expected_type,
        source_file=pdf_path.name,
    )

    try:
        # Check if file exists
        if not pdf_path.exists():
            record.status = "error"
            record.error = f"PDF file not found: {pdf_path}"
            return record

        # Run extraction through router
        blocks = extract_page_products(
            pdf_path=pdf_path,
            page_number=page_number,
            brand_hint=brand_hint,
            source_file=pdf_path.name,
        )

        # Convert router blocks to products
        products = convert_blocks_to_products(blocks)

        # Fallback for single-detail product pages
        if not products and expected_type == "product_cards":
            products = extract_single_detail_product(
                pdf_path=pdf_path,
                page_number=page_number,
                brand_hint=brand_hint,
            )

        record.products = products
        record.products_found = len(products)
        record.has_sku = any(bool(p.sku) for p in products)
        record.has_name = any(bool(p.name) for p in products)

        # Determine status
        if not products:
            if expected_type in {"grid_catalog", "unknown"}:
                record.status = "skipped"
                record.skip_reason = (
                    "overview/index page; detailed products appear later"
                )
            else:
                record.status = "empty"
                record.skip_reason = None
        else:
            record.status = "success"
            record.skip_reason = None

        logger.info(
            "Page %d (%s): %s - %d products",
            page_number,
            expected_type,
            record.status,
            len(products),
        )

    except Exception as e:
        record.status = "error"
        record.error = f"{type(e).__name__}: {str(e)}"
        logger.error("Page %d (%s): ERROR - %s", page_number, expected_type, e)

    return record


# =============================================================================
# Summary & Reporting
# =============================================================================


def calculate_summary(records: list[ExtractionAuditRecord]) -> ExtractionAuditSummary:
    """Calculate summary statistics from audit records."""
    summary = ExtractionAuditSummary()

    summary.total_pages_tested = len(records)

    for record in records:
        # Count by type
        summary.pages_by_type[record.page_type] = (
            summary.pages_by_type.get(record.page_type, 0) + 1
        )

        # Count by status
        if record.status == "success":
            summary.successful_pages += 1
        elif record.status == "error":
            summary.error_pages += 1
            error_type = record.error.split(":")[0] if record.error else "Unknown"
            summary.errors_by_type[error_type] = (
                summary.errors_by_type.get(error_type, 0) + 1
            )
        elif record.status == "empty":
            summary.empty_pages += 1
        elif record.status == "skipped":
            summary.skipped_pages += 1

        # Count products
        summary.total_products_extracted += record.products_found

        # Track pages without SKU/name
        if record.products_found > 0:
            if not record.has_sku:
                summary.pages_without_sku += 1
            if not record.has_name:
                summary.pages_without_name += 1

    return summary


def print_summary(summary: ExtractionAuditSummary) -> None:
    """Print formatted summary to console."""
    print("\n" + "=" * 60)
    print("EXTRACTION AUDIT SUMMARY")
    print("=" * 60)

    print(f"\nTotal pages tested: {summary.total_pages_tested}")

    print("\nBy page type:")
    for page_type, count in sorted(summary.pages_by_type.items()):
        print(f"  {page_type:20s}: {count:3d} pages")

    print("\nExtraction results:")
    print(f"  Successful pages : {summary.successful_pages}")
    print(f"  Error pages      : {summary.error_pages}")
    print(f"  Empty pages      : {summary.empty_pages}")
    print(f"  Skipped pages    : {summary.skipped_pages}")

    print(f"\nProducts extracted: {summary.total_products_extracted}")

    print("\nQuality metrics:")
    print(f"  Pages without SKU : {summary.pages_without_sku}")
    print(f"  Pages without name: {summary.pages_without_name}")

    if summary.errors_by_type:
        print("\nError breakdown:")
        for error_type, count in sorted(
            summary.errors_by_type.items(), key=lambda x: -x[1]
        ):
            print(f"  {error_type}: {count}")

    print("\n" + "=" * 60)


# =============================================================================
# Main Entry Point
# =============================================================================


def main() -> int:
    """Main entry point for extraction audit script."""
    logger.info("Starting extraction audit")
    logger.info("Project root: %s", project_root)

    # Parse audit file
    logger.info("Parsing audit file: %s", AUDIT_FILE)
    pages_by_type = parse_audit_file(AUDIT_FILE)

    if not pages_by_type:
        logger.error("No pages found in audit file")
        return 1

    # Select test sample
    test_pages = select_test_sample(pages_by_type, SAMPLE_CONFIG)

    if not test_pages:
        logger.error("No test pages selected")
        return 1

    logger.info("Testing %d pages", len(test_pages))

    # Find PDF file
    pdf_path = project_root / PDF_FILENAME
    if not pdf_path.exists():
        # Try to find any PDF file
        pdf_files = list(project_root.glob("*.pdf"))
        if pdf_files:
            pdf_path = pdf_files[0]
            logger.info("Using PDF: %s", pdf_path.name)
        else:
            logger.error("No PDF file found in project root")
            return 1

    # Extract brand hint from filename
    brand_hint = None
    if "gappo" in pdf_path.name.lower():
        brand_hint = "GAPPO"
    elif "frap" in pdf_path.name.lower():
        brand_hint = "FRAP"

    logger.info("Brand hint: %s", brand_hint or "None")

    # Process each test page
    records: list[ExtractionAuditRecord] = []

    for page_num, page_type in test_pages:
        record = extract_from_page(
            pdf_path=pdf_path,
            page_number=page_num,
            expected_type=page_type,
            brand_hint=brand_hint,
        )
        records.append(record)

    # Save results to JSONL
    output_path = project_root / OUTPUT_FILE
    logger.info("Saving results to: %s", output_path)

    with open(output_path, "w", encoding="utf-8") as f:
        for record in records:
            f.write(record.model_dump_json() + "\n")

    logger.info("Saved %d records", len(records))

    # Calculate and print summary
    summary = calculate_summary(records)
    print_summary(summary)

    # Also save summary as JSON
    summary_path = output_path.with_suffix(".summary.json")
    summary_path.write_text(summary.model_dump_json(indent=2), encoding="utf-8")
    logger.info("Summary saved to: %s", summary_path)

    return 0


if __name__ == "__main__":
    sys.exit(main())
