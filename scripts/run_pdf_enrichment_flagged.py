#!/usr/bin/env python3
"""
PDF Enrichment Script for Flagged Products.

Enriches product data from PDF catalogs for products marked with
needs_pdf_enrichment=true flag.

Usage:
    # Dry run - preview changes without modifying database
    python -m scripts.run_pdf_enrichment_flagged --dry-run --limit 50

    # Apply changes to database
    python -m scripts.run_pdf_enrichment_flagged --apply

    # Aggressive mode (replace more names)
    python -m scripts.run_pdf_enrichment_flagged --apply --mode aggressive

    # Verbose output
    python -m scripts.run_pdf_enrichment_flagged --dry-run --verbose

    # Use SQLite database
    python -m scripts.run_pdf_enrichment_flagged --dry-run --use-sqlite
"""

from __future__ import annotations

import argparse
import logging
import sys
import os
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Configure logging BEFORE importing app modules
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


def get_session(use_sqlite: bool = False):
    """Get database session based on configuration."""
    if use_sqlite or os.getenv("USE_SQLITE", "").lower() == "true":
        from app.db.session_sqlite import get_sqlite_session

        logger.info("Using SQLite database (test.db)")
        return get_sqlite_session()
    else:
        from app.db.session import SessionLocal

        logger.info("Using PostgreSQL database")
        return SessionLocal()


def find_pdf_catalogs() -> list[Path]:
    """Find PDF catalog files in the project."""
    project_root = Path(__file__).parent.parent

    # Look for PDF files in common locations
    search_paths = [
        project_root,
        project_root / "storage",
        project_root / "documents",
        project_root / "catalogs",
    ]

    pdfs = []
    for search_path in search_paths:
        if search_path.exists():
            pdfs.extend(search_path.glob("*.pdf"))

    # Filter out non-catalog PDFs (receipts, manuals, etc)
    catalog_keywords = ["каталог", "catalog", "прайс", "price", "gappo"]

    catalogs = []
    for pdf in pdfs:
        pdf_lower = pdf.name.lower()
        if any(keyword in pdf_lower for keyword in catalog_keywords):
            catalogs.append(pdf)
        elif "каталог" in pdf_lower or "catalog" in pdf_lower:
            catalogs.append(pdf)

    # If no catalogs found by keyword, use all PDFs
    if not catalogs and pdfs:
        catalogs = pdfs

    return catalogs


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Enrich flagged products from PDF catalogs",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Preview changes for first 50 products
  python -m scripts.run_pdf_enrichment_flagged --dry-run --limit 50
  
  # Apply changes to all flagged products
  python -m scripts.run_pdf_enrichment_flagged --apply
  
  # Aggressive mode - replace more names
  python -m scripts.run_pdf_enrichment_flagged --apply --mode aggressive
  
  # Verbose logging
  python -m scripts.run_pdf_enrichment_flagged --dry-run --verbose
  
  # Use SQLite database instead of PostgreSQL
  python -m scripts.run_pdf_enrichment_flagged --dry-run --use-sqlite
        """,
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview changes without modifying database (default)",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply changes to database",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Limit number of products to process",
    )
    parser.add_argument(
        "--mode",
        type=str,
        choices=["conservative", "aggressive"],
        default="conservative",
        help="Replacement strategy: conservative (default) or aggressive",
    )
    parser.add_argument(
        "--pdf-paths",
        type=str,
        nargs="+",
        default=None,
        help="Specific PDF file paths to use (optional)",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose output",
    )
    parser.add_argument(
        "--no-pdfs-auto",
        action="store_true",
        help="Don't auto-discover PDFs (require explicit --pdf-paths)",
    )
    parser.add_argument(
        "--use-sqlite",
        action="store_true",
        help="Use SQLite database (test.db) instead of PostgreSQL",
    )

    return parser.parse_args()


def validate_setup(pdf_paths: list[Path]) -> bool:
    """Validate that everything is ready to run."""
    if not pdf_paths:
        print("ERROR: No PDF catalog files found or provided.")
        print(
            "Please provide PDF paths with --pdf-paths or place catalogs in project root."
        )
        return False

    valid_pdfs = []
    for pdf_path in pdf_paths:
        if pdf_path.exists():
            valid_pdfs.append(pdf_path)
        else:
            print(f"WARNING: PDF not found: {pdf_path}")

    if not valid_pdfs:
        print("ERROR: No valid PDF files found.")
        return False

    print(f"Using {len(valid_pdfs)} PDF catalog(s):")
    for pdf in valid_pdfs:
        print(f"  - {pdf.name}")

    return True


def main() -> int:
    """Main entry point."""
    args = parse_args()

    # Import after setting up logging
    from app.services.pdf_enrichment import PdfEnrichmentService

    # Set logging level
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
        logging.getLogger("app.services.pdf_enrichment").setLevel(logging.DEBUG)

    # Determine mode
    if args.apply:
        mode = "apply"
    else:
        mode = "dry_run"
        if not args.dry_run and not args.apply:
            print("No action specified, defaulting to --dry-run")
            print("Use --apply to make actual changes\n")

    # Get PDF paths
    if args.pdf_paths:
        pdf_paths = [Path(p) for p in args.pdf_paths]
    elif not args.no_pdfs_auto:
        pdf_paths = find_pdf_catalogs()
    else:
        pdf_paths = []

    # Validate
    if not validate_setup(pdf_paths):
        return 1

    # Create database session
    session = get_session(use_sqlite=args.use_sqlite)

    try:
        dump_paths = [
            r"storage\pdf_cache\gappo_2026_pages_023_072.json",
            r"storage\pdf_cache\gappo_2026_pages_073_122.json",
            r"storage\pdf_cache\gappo_2026_pages_123_172.json",
            r"storage\pdf_cache\gappo_2026_pages_173_222.json",
            r"storage\pdf_cache\gappo_2026_pages_223_272.json",
            r"storage\pdf_cache\gappo_2026_pages_273_322.json",
            r"storage\pdf_cache\gappo_2026_pages_323_372.json",
            r"storage\pdf_cache\gappo_2026_pages_373_402.json",
        ]

        index_paths = [
            r"storage\pdf_cache\gappo_2026_sku_index_023_072.json",
            r"storage\pdf_cache\gappo_2026_sku_index_073_122.json",
            r"storage\pdf_cache\gappo_2026_sku_index_123_172.json",
            r"storage\pdf_cache\gappo_2026_sku_index_173_222.json",
            r"storage\pdf_cache\gappo_2026_sku_index_223_272.json",
            r"storage\pdf_cache\gappo_2026_sku_index_273_322.json",
            r"storage\pdf_cache\gappo_2026_sku_index_323_372.json",
            r"storage\pdf_cache\gappo_2026_sku_index_373_402.json",
        ]

        # Create service
        service = PdfEnrichmentService(
            session=session,
            dump_paths=dump_paths,
            index_paths=index_paths,
            mode=args.mode,
        )

        # Count flagged products first
        flagged = service.get_flagged_products()
        print(f"\nFound {len(flagged)} products flagged for PDF enrichment")

        if args.limit:
            print(f"Will process: {min(args.limit, len(flagged))} products")

        if mode == "dry_run":
            print("\n" + "=" * 60)
            print("RUNNING DRY-RUN MODE")
            print("No database changes will be made")
            print("=" * 60 + "\n")

            result = service.run_dry_run(limit=args.limit, verbose=args.verbose)
            service.print_dry_run_report(result)

            # Summary for programmatic use
            summary = service.build_summary(result, "dry_run")

            print(f"\nSUMMARY:")
            print(f"  Total flagged: {summary.total_flagged}")
            print(f"  Matched in PDF: {summary.matched}")
            print(f"  Name replacements planned: {summary.name_replacements_planned}")
            print(
                f"  Description updates planned: {summary.description_updates_planned}"
            )

        else:  # apply mode
            print("\n" + "=" * 60)
            print("RUNNING APPLY MODE")
            print("Database will be modified!")
            print("=" * 60 + "\n")

            # Safety confirmation
            if not args.limit and len(flagged) > 10:
                response = input(
                    f"Are you sure you want to update {len(flagged)} products? [yes/no]: "
                )
                if response.lower() != "yes":
                    print("Aborted.")
                    return 0

            result = service.run_apply(limit=args.limit, verbose=args.verbose)
            service.print_apply_report(result)

            summary = service.build_summary(result, "apply")

            print(f"\nSUMMARY:")
            print(f"  Total processed: {summary.total_flagged}")
            print(f"  Matched in PDF: {summary.matched}")
            print(f"  Names updated: {summary.updated_name}")
            print(f"  Descriptions updated: {summary.updated_description}")
            print(f"  Flags cleared: {summary.cleared_needs_pdf_enrichment}")
            print(f"  Failed: {summary.failed}")

        return 0

    except Exception as e:
        logger.exception("Enrichment failed")
        print(f"\nERROR: {e}")
        return 1

    finally:
        session.close()


if __name__ == "__main__":
    sys.exit(main())
