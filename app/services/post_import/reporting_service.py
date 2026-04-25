"""Post-import summary reporting service for Santeh Catalog.

Provides unified summary report after any import operation (products or stock).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


@dataclass
class PostImportReport:
    """Unified post-import summary report."""

    # Source info
    run_type: str  # "product_import" | "stock_import" | "backfill" | etc.
    source_file: Optional[str] = None
    dry_run: bool = True
    generated_at: datetime = field(default_factory=datetime.utcnow)

    # Row counts (universal)
    rows_scanned: int = 0
    inserted_count: int = 0
    updated_count: int = 0

    # Skip reasons (stock import)
    skipped_duplicate_sku: int = 0
    skipped_invalid_sku: int = 0
    skipped_invalid_qty: int = 0
    skipped_no_product: int = 0

    # Matching (stock import)
    unmatched_sku_count: int = 0
    unmatched_skus: list[str] = field(default_factory=list)

    # Brand audit (universal)
    brand_overrides_applied: int = 0
    total_brand_null: int = 0
    final_brand_distribution: dict[str, int] = field(default_factory=dict)

    # Error state
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)

    def to_json(self, indent: int = 2) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), indent=indent, default=str)

    def validate_invariants(self) -> None:
        """Validate critical invariants and raise if violated.

        Raises:
            PostImportInvariantError: if total_brand_null != 0
        """
        # Skip validation if brand audit wasn't performed (dry-run marker)
        if self.total_brand_null == -1:
            return

        if self.total_brand_null != 0:
            raise PostImportInvariantError(
                f"INVARIANT VIOLATED: total_brand_null={self.total_brand_null} "
                f"(expected 0). Run failed."
            )

    def log_summary(self) -> None:
        """Log human-readable summary."""
        logger.info("=" * 70)
        logger.info("POST-IMPORT SUMMARY REPORT")
        logger.info("=" * 70)
        logger.info(f"Run type:        {self.run_type}")
        logger.info(f"Source:          {self.source_file or 'N/A'}")
        logger.info(f"Dry run:         {self.dry_run}")
        logger.info(f"Generated:       {self.generated_at.isoformat()}")
        logger.info("-" * 70)
        logger.info("ROW COUNTS")
        logger.info(f"  Scanned:       {self.rows_scanned}")
        logger.info(f"  Inserted:      {self.inserted_count}")
        logger.info(f"  Updated:       {self.updated_count}")
        logger.info("-" * 70)
        logger.info("SKIP REASONS")
        logger.info(f"  Duplicate SKU: {self.skipped_duplicate_sku}")
        logger.info(f"  Invalid SKU:   {self.skipped_invalid_sku}")
        logger.info(f"  Invalid Qty:   {self.skipped_invalid_qty}")
        logger.info(f"  No product:    {self.skipped_no_product}")
        logger.info("-" * 70)
        logger.info("MATCHING")
        logger.info(f"  Unmatched:     {self.unmatched_sku_count}")
        if self.unmatched_skus:
            logger.info(f"  Unmatched SKUs (first 10): {self.unmatched_skus[:10]}")
        logger.info("-" * 70)
        logger.info("BRAND AUDIT")
        logger.info(f"  Overrides:     {self.brand_overrides_applied}")
        if self.total_brand_null == -1:
            logger.info("  NULL brands:   N/A (dry-run)")
            logger.info("  ○ Brand audit: SKIPPED (dry-run)")
        elif self.total_brand_null == 0:
            logger.info(f"  NULL brands:   {self.total_brand_null}")
            logger.info("  ✓ Brand invariant: PASSED")
        else:
            logger.info(f"  NULL brands:   {self.total_brand_null}")
            logger.info("  ✗ Brand invariant: FAILED")
        if self.final_brand_distribution:
            logger.info("  Distribution:")
            for brand, count in sorted(self.final_brand_distribution.items()):
                logger.info(f"    {brand}: {count}")
        logger.info("=" * 70)

        if self.errors:
            logger.warning("ERRORS DURING RUN:")
            for err in self.errors:
                logger.warning(f"  - {err}")


class PostImportInvariantError(Exception):
    """Raised when post-import invariant is violated."""

    pass


class PostImportReporter:
    """Service for building and validating post-import reports."""

    def __init__(self, session: Session):
        self.session = session

    def build_from_stock_result(
        self,
        stock_result: Any,  # StockImportCommitResult or StockMatchReport
        brand_result: Optional[Any] = None,
        run_type: str = "stock_import",
        source_file: Optional[str] = None,
        dry_run: bool = True,
    ) -> PostImportReport:
        """Build report from stock import result."""

        report = PostImportReport(
            run_type=run_type,
            source_file=source_file,
            dry_run=dry_run,
        )

        # Extract from stock result (StockImportCommitResult)
        if hasattr(stock_result, "rows_scanned_from_source"):
            report.rows_scanned = stock_result.rows_scanned_from_source
            report.updated_count = getattr(stock_result, "updated", 0)
            # Note: inserted_count is typically 0 for stock import (updates only)
            report.skipped_duplicate_sku = getattr(stock_result, "skipped_duplicate", 0)
            report.skipped_invalid_sku = getattr(stock_result, "skipped_invalid_sku", 0)
            report.skipped_invalid_qty = getattr(stock_result, "skipped_invalid_qty", 0)
            report.skipped_no_product = getattr(stock_result, "skipped_no_product", 0)
            report.unmatched_sku_count = getattr(stock_result, "skipped_no_product", 0)
        elif hasattr(stock_result, "total_rows_scanned"):
            # From StockMatchReport (dry-run)
            report.rows_scanned = stock_result.total_rows_scanned
            report.skipped_duplicate_sku = getattr(
                stock_result, "duplicate_sku_in_source", 0
            )
            report.skipped_invalid_sku = getattr(stock_result, "skipped_invalid_sku", 0)
            report.skipped_invalid_qty = getattr(stock_result, "invalid_qty", 0)
            report.unmatched_sku_count = getattr(stock_result, "unmatched_in_db", 0)

        # Extract unmatched SKUs if available
        if hasattr(stock_result, "get_unmatched_report"):
            unmatched_report = stock_result.get_unmatched_report()
            if hasattr(unmatched_report, "unmatched_results"):
                report.unmatched_skus = [
                    r.normalized_sku
                    for r in unmatched_report.unmatched_results
                    if r.normalized_sku
                ]
        elif hasattr(stock_result, "results"):
            # From StockMatchReport
            report.unmatched_skus = [
                r.normalized_sku
                for r in stock_result.results
                if r.match_status == "unmatched" and r.normalized_sku
            ]

        # Add brand info (only for commit runs)
        if brand_result:
            report.brand_overrides_applied = getattr(brand_result, "updated_rows", 0)
            report.total_brand_null = getattr(brand_result, "total_brand_null", 0)

        # Get brand distribution from DB (only for commit runs)
        if not dry_run:
            report.final_brand_distribution = self._get_brand_distribution()

        return report

    def build_from_product_import(
        self,
        import_result: Any,  # ImportResult from product importer
        brand_result: Optional[Any] = None,
        source_file: Optional[str] = None,
        dry_run: bool = True,
    ) -> PostImportReport:
        """Build report from product import result."""

        report = PostImportReport(
            run_type="product_import",
            source_file=source_file,
            dry_run=dry_run,
        )

        # Extract from product import result
        report.rows_scanned = getattr(import_result, "total", 0)
        report.inserted_count = getattr(import_result, "created", 0)
        report.updated_count = getattr(import_result, "updated", 0)

        # Add brand info
        if dry_run:
            report.total_brand_null = -1
        else:
            if brand_result:
                report.brand_overrides_applied = getattr(
                    brand_result, "updated_rows", 0
                )
                report.total_brand_null = getattr(brand_result, "total_brand_null", 0)

        # Get brand distribution from DB
        report.final_brand_distribution = self._get_brand_distribution()

        return report

    def _get_brand_distribution(self) -> dict[str, int]:
        """Get current brand distribution from database."""
        try:
            result = self.session.execute(
                text(
                    """
                SELECT brand, COUNT(*) as cnt
                FROM products
                WHERE brand IS NOT NULL
                GROUP BY brand
                ORDER BY cnt DESC
            """
                )
            )
            return {row[0]: row[1] for row in result}
        except Exception as e:
            logger.warning(f"Failed to get brand distribution: {e}")
            return {}

    def save_report_artifact(
        self,
        report: PostImportReport,
        output_dir: Path = Path("reports"),
    ) -> Path:
        """Save report as JSON artifact."""
        output_dir.mkdir(parents=True, exist_ok=True)

        timestamp = report.generated_at.strftime("%Y%m%d_%H%M%S")
        filename = f"import_report_{report.run_type}_{timestamp}.json"
        filepath = output_dir / filename

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(report.to_json())

        logger.info(f"Report saved to: {filepath}")
        return filepath

    def save_unmatched_skus(
        self,
        report: PostImportReport,
        output_dir: Path = Path("reports"),
    ) -> Optional[Path]:
        """Save unmatched SKUs to separate file if any."""
        if not report.unmatched_skus:
            return None

        output_dir.mkdir(parents=True, exist_ok=True)

        timestamp = report.generated_at.strftime("%Y%m%d_%H%M%S")
        filename = f"unmatched_skus_{timestamp}.txt"
        filepath = output_dir / filename

        with open(filepath, "w", encoding="utf-8") as f:
            f.write(f"# Unmatched SKUs from {report.run_type}\\n")
            f.write(f"# Generated: {report.generated_at.isoformat()}\\n")
            f.write(f"# Count: {len(report.unmatched_skus)}\\n")
            f.write("-" * 40 + "\\n")
            for sku in sorted(set(report.unmatched_skus)):
                f.write(f"{sku}\\n")

        logger.info(f"Unmatched SKUs saved to: {filepath}")
        return filepath


def run_post_import_summary(
    session: Session,
    stock_result: Optional[Any] = None,
    product_result: Optional[Any] = None,
    brand_result: Optional[Any] = None,
    run_type: str = "unknown",
    source_file: Optional[str] = None,
    dry_run: bool = True,
    save_artifacts: bool = True,
    validate: bool = False,
) -> PostImportReport:
    """Convenience function to generate and validate post-import summary.

    This is the main entry point - call this at the end of any import run.

    Args:
        session: Database session
        stock_result: Result from stock import (optional)
        product_result: Result from product import (optional)
        brand_result: Result from brand overrides (optional)
        run_type: Type of run
        source_file: Source file path
        dry_run: Whether this was dry-run
        save_artifacts: Whether to save report files
        validate: Whether to validate invariants (raises if failed)

    Returns:
        PostImportReport

    Raises:
        PostImportInvariantError: if validate=True and invariants violated
    """
    reporter = PostImportReporter(session)

    # Build appropriate report type
    if stock_result:
        report = reporter.build_from_stock_result(
            stock_result=stock_result,
            brand_result=brand_result,
            run_type=run_type,
            source_file=source_file,
            dry_run=dry_run,
        )
    elif product_result:
        report = reporter.build_from_product_import(
            import_result=product_result,
            brand_result=brand_result,
            source_file=source_file,
            dry_run=dry_run,
        )
    else:
        # Minimal report with just brand audit
        report = PostImportReport(
            run_type=run_type,
            source_file=source_file,
            dry_run=dry_run,
        )
        if brand_result:
            report.brand_overrides_applied = getattr(brand_result, "updated_rows", 0)
            report.total_brand_null = getattr(brand_result, "total_brand_null", 0)
        report.final_brand_distribution = reporter._get_brand_distribution()

    # Log the summary
    report.log_summary()

    # Save artifacts
    if save_artifacts:
        reporter.save_report_artifact(report)
        reporter.save_unmatched_skus(report)

    # Validate invariants
    if validate:
        report.validate_invariants()

    return report
