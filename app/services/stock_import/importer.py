"""Stock importer with commit logic.

Updates only inventory fields, never creates products or changes catalog.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from sqlalchemy.orm import Session

from app.db import models
from app.repositories.inventory import InventoryRepository
from app.repositories.product import ProductRepository
from app.schemas import InventoryUpdate
from app.utils.stock_parser import ParsedStockValue, parse_stock_value_for_update
from .matcher import StockMatcher, StockMatchReport

logger = logging.getLogger(__name__)


@dataclass
class StockUpdateRecord:
    """Record of a single stock update."""

    product_id: int
    sku: str
    old_stock_doc: float
    new_stock_doc: float
    raw_value: any
    parsed_value: ParsedStockValue
    source_file: str
    imported_at: datetime


@dataclass
class ImportSummary:
    """Comprehensive summary of a stock import run.

    All counters should be consistent and auditable.
    """

    # Source stats
    rows_scanned: int

    # Product outcomes
    inserted_count: int = 0  # New products created (usually 0 for stock import)
    updated_count: int = 0  # Stock values updated

    # Skip reasons
    skipped_duplicate_sku: int = 0
    skipped_invalid_sku: int = 0
    skipped_invalid_qty: int = 0
    skipped_no_product: int = 0  # Unmatched SKUs

    # Matching stats
    unmatched_sku_count: int = 0

    # Brand audit
    brand_overrides_applied: int = 0
    total_brand_null: int = 0
    final_brand_distribution: dict[str, int] = field(default_factory=dict)

    # Reference data
    unmatched_skus: list[str] = field(default_factory=list)
    source_file: str = ""

    def log_summary(self, logger: logging.Logger) -> None:
        """Log comprehensive summary at end of import run."""
        logger.info("=" * 70)
        logger.info("IMPORT SUMMARY REPORT")
        logger.info("=" * 70)
        logger.info(f"Source file: {self.source_file}")
        logger.info(f"Rows scanned: {self.rows_scanned}")
        logger.info("-" * 70)
        logger.info(f"Products updated: {self.updated_count}")
        logger.info(f"Products unchanged: {self.inserted_count}")  # Reuse for unchanged
        logger.info("-" * 70)
        logger.info(f"Skipped (duplicate SKU): {self.skipped_duplicate_sku}")
        logger.info(f"Skipped (invalid SKU): {self.skipped_invalid_sku}")
        logger.info(f"Skipped (invalid qty): {self.skipped_invalid_qty}")
        logger.info(f"Skipped (no product in DB): {self.skipped_no_product}")
        logger.info("-" * 70)
        logger.info(f"Unmatched SKU count: {self.unmatched_sku_count}")
        if self.unmatched_skus:
            logger.info(f"Unmatched SKUs (first 20): {self.unmatched_skus[:20]}")
        logger.info("-" * 70)
        logger.info(f"Brand overrides applied: {self.brand_overrides_applied}")
        logger.info(f"Total brand NULL: {self.total_brand_null}")
        logger.info(f"Brand distribution: {dict(self.final_brand_distribution)}")
        logger.info("=" * 70)

        if self.total_brand_null != 0:
            logger.error(
                f"CRITICAL: total_brand_null = {self.total_brand_null} - THIS MUST BE ZERO!"
            )

        if self.unmatched_sku_count > 0:
            logger.warning(
                f"There are {self.unmatched_sku_count} unmatched SKUs that need attention"
            )

    def to_dict(self) -> dict:
        """Convert to dict for JSON serialization."""
        return {
            "rows_scanned": self.rows_scanned,
            "inserted_count": self.inserted_count,
            "updated_count": self.updated_count,
            "skipped_duplicate_sku": self.skipped_duplicate_sku,
            "skipped_invalid_sku": self.skipped_invalid_sku,
            "skipped_invalid_qty": self.skipped_invalid_qty,
            "skipped_no_product": self.skipped_no_product,
            "unmatched_sku_count": self.unmatched_sku_count,
            "brand_overrides_applied": self.brand_overrides_applied,
            "total_brand_null": self.total_brand_null,
            "final_brand_distribution": dict(self.final_brand_distribution),
            "unmatched_skus": self.unmatched_skus,
            "source_file": self.source_file,
        }


@dataclass
class StockImportCommitResult:
    """Result of committing stock imports.

    All row counts should sum to rows_scanned_from_source.
    """

    # Source stats
    rows_scanned_from_source: int

    # Processing outcomes (should sum to rows_scanned_from_source)
    updated: int  # Successfully updated inventory
    unchanged: int  # Matched but qty unchanged
    skipped_duplicate: int  # Skipped due to duplicate in source
    skipped_no_product: int  # Unmatched in DB
    skipped_unsupported_brand: int  # Filtered by brand (not FRAP or GAPPO)
    skipped_invalid_sku: int  # Empty/invalid SKU
    skipped_invalid_qty: int  # Invalid quantity (Excel errors like #REF!, #N/A, etc.)
    empty_qty_treated_as_zero: int  # Empty qty interpreted as 0 (valid, not skipped)
    errors: int  # Exceptions during processing

    # Legacy field for backward compatibility
    skipped_non_frap: int = 0

    # Brand tracking for summary
    brand_overrides_applied: int = 0
    final_brand_distribution: dict = field(default_factory=dict)

    # Unmatched SKUs for reporting
    unmatched_skus: list[str] = field(default_factory=list)

    updates: list[StockUpdateRecord] = field(default_factory=list)

    def generate_summary(self, source_file: str = "") -> ImportSummary:
        """Generate comprehensive ImportSummary from commit result.

        Args:
            source_file: Original source filename for reference

        Returns:
            ImportSummary with complete audit information
        """

        # Count NULL brands from final distribution
        null_brand_count = (
            self.final_brand_distribution.get(None, 0)
            + self.final_brand_distribution.get("", 0)
            + self.final_brand_distribution.get("NULL", 0)
        )

        return ImportSummary(
            rows_scanned=self.rows_scanned_from_source,
            inserted_count=self.unchanged,  # unchanged = processed but not updated
            updated_count=self.updated,
            skipped_duplicate_sku=self.skipped_duplicate,
            skipped_invalid_sku=self.skipped_invalid_sku,
            skipped_invalid_qty=self.skipped_invalid_qty,
            skipped_no_product=self.skipped_no_product,
            unmatched_sku_count=len(self.unmatched_skus),
            brand_overrides_applied=self.brand_overrides_applied,
            total_brand_null=null_brand_count,
            final_brand_distribution=dict(self.final_brand_distribution),
            unmatched_skus=self.unmatched_skus,
            source_file=source_file,
        )

    def print_summary(self) -> None:
        """Print summary of commit operation."""
        total_accounted = (
            self.updated
            + self.unchanged
            + self.skipped_duplicate
            + self.skipped_no_product
            + self.skipped_unsupported_brand
            + self.skipped_invalid_sku
            + self.skipped_invalid_qty
            + self.errors
        )

        print("\n" + "=" * 60)
        print("STOCK IMPORT COMMIT RESULTS")
        print("=" * 60)
        print(f"Rows scanned from source: {self.rows_scanned_from_source}")
        print("-" * 60)
        print(f"  Updated:                   {self.updated}")
        print(f"  Unchanged (same qty):      {self.unchanged}")
        print(f"  Skipped (duplicate):       {self.skipped_duplicate}")
        print(f"  Skipped (no product):      {self.skipped_no_product}")
        print(f"  Skipped (unsupported brand): {self.skipped_unsupported_brand}")
        print(f"  Skipped (invalid SKU):     {self.skipped_invalid_sku}")
        print(f"  Skipped (invalid qty):     {self.skipped_invalid_qty}")
        print(f"  Empty qty as zero:         {self.empty_qty_treated_as_zero}")
        print(f"  Errors:                    {self.errors}")
        print("-" * 60)
        print(f"  TOTAL ACCOUNTED:           {total_accounted}")

        if total_accounted != self.rows_scanned_from_source:
            print(f"  ⚠️  MISMATCH: expected {self.rows_scanned_from_source}")
        else:
            print("  ✓ All rows accounted for")
        print("=" * 60)


class StockImporter:
    """Safe stock importer with dry-run and commit modes."""

    def __init__(
        self,
        session: Session,
        source_file: str,
        source_name: str = "stock_excel",
    ):
        """
        Args:
            session: Database session
            source_file: Path to source Excel file
            source_name: Identifier for this import source
        """
        self.session = session
        self.source_file = source_file
        self.source_name = source_name
        self.product_repo = ProductRepository(session)
        self.inventory_repo = InventoryRepository(session)
        # Support both FRAP and GAPPO brands
        self.matcher = StockMatcher(session, brand_filter=None)

    def dry_run(self, report: StockMatchReport) -> None:
        """Execute dry-run and print report."""
        report.print_report()
        report.print_duplicate_warning()
        report.print_detailed_report()

        print(f"\n--- DRY RUN COMPLETE ---")
        print(f"No changes were made to the database.")
        print(f"Run with --commit to apply {report.planned_updates} updates.")

    def commit(
        self, report: StockMatchReport, skip_duplicates: bool = True
    ) -> StockImportCommitResult:
        """Commit matched stock updates to database.

        Args:
            report: Match report from dry-run
            skip_duplicates: If True, skip SKUs that appear multiple times in source

        Returns:
            StockImportCommitResult with details of all changes
        """
        result = StockImportCommitResult(
            rows_scanned_from_source=len(report.results),
            updated=0,
            unchanged=0,
            skipped_duplicate=0,
            skipped_no_product=0,
            skipped_unsupported_brand=0,
            skipped_invalid_sku=0,
            skipped_invalid_qty=0,
            empty_qty_treated_as_zero=0,
            errors=0,
            brand_overrides_applied=0,
            final_brand_distribution={},
            unmatched_skus=[],
        )

        # Brand tracking
        brand_distribution: dict[str, int] = {}

        # Get list of duplicate SKUs to skip
        duplicate_skus = set(report.duplicate_skus.keys()) if skip_duplicates else set()

        if duplicate_skus:
            logger.warning(
                f"Skipping {len(duplicate_skus)} duplicate SKUs: {duplicate_skus}"
            )

        imported_at = datetime.utcnow()

        for match_result in report.results:
            status = match_result.match_status

            # Track brand from matcher (before any processing)
            brand = match_result.brand_derived or "UNKNOWN"
            brand_distribution[brand] = brand_distribution.get(brand, 0) + 1

            # Handle each status explicitly for complete accounting
            if status == "unsupported_brand":
                result.skipped_unsupported_brand += 1
                continue

            if status == "skipped_non_frap":
                result.skipped_unsupported_brand += 1
                result.skipped_non_frap += 1  # Legacy
                continue

            if status == "invalid_sku":
                result.skipped_invalid_sku += 1
                continue

            if status == "invalid_qty":
                result.skipped_invalid_qty += 1
                continue

            if status == "unmatched":
                result.skipped_no_product += 1
                # Collect unmatched SKU for reporting
                if match_result.normalized_sku:
                    result.unmatched_skus.append(match_result.normalized_sku)
                continue

            if status == "duplicate":
                # This shouldn't happen in normal flow, but handle it
                result.skipped_duplicate += 1
                continue

            if status != "matched":
                # Unknown status - log and count as error
                logger.warning(
                    f"Unknown match_status '{status}' for row {match_result.row_index}"
                )
                result.errors += 1
                continue

            # From here: status == "matched"

            # Track empty qty treated as zero
            if match_result.parsed_qty.parse_status == "empty":
                result.empty_qty_treated_as_zero += 1

            # Skip duplicates if requested (additional policy check)
            if skip_duplicates and match_result.normalized_sku in duplicate_skus:
                result.skipped_duplicate += 1
                logger.debug(f"Skipping duplicate SKU: {match_result.normalized_sku}")
                continue

            # Get current inventory state
            try:
                product = self.product_repo.get(match_result.product_id)
                if not product:
                    logger.error(
                        f"Product {match_result.product_id} disappeared during import"
                    )
                    result.errors += 1
                    continue

                # Track final brand from product (post-override)
                final_brand = product.brand or "NULL"
                result.final_brand_distribution[final_brand] = (
                    result.final_brand_distribution.get(final_brand, 0) + 1
                )

                # Check for brand override
                if match_result.brand_derived and product.brand != match_result.brand_derived:
                    # Brand was overridden during import process
                    result.brand_overrides_applied += 1
                    logger.debug(
                        f"Brand override for {match_result.normalized_sku}: "
                        f"{match_result.brand_derived} -> {product.brand}"
                    )

                current_inventory = self.inventory_repo.get_by_product_id(product.id)
                old_stock_doc = (
                    current_inventory.stock_doc if current_inventory else 0.0
                )

                # Calculate new stock value
                new_stock_doc = parse_stock_value_for_update(match_result.raw_qty)
                if new_stock_doc is None:
                    # Fallback to min for ranges
                    new_stock_doc = match_result.parsed_qty.stock_min or 0

                # Check if actually changed
                if old_stock_doc == new_stock_doc:
                    result.unchanged += 1
                    logger.debug(
                        f"No change for SKU {match_result.normalized_sku}: {old_stock_doc}"
                    )
                    continue

                # Update inventory
                update_data = InventoryUpdate(stock_doc=float(new_stock_doc))
                self.inventory_repo.upsert(product.id, update_data)

                # Record the update
                record = StockUpdateRecord(
                    product_id=product.id,
                    sku=match_result.normalized_sku,
                    old_stock_doc=float(old_stock_doc),
                    new_stock_doc=float(new_stock_doc),
                    raw_value=match_result.raw_qty,
                    parsed_value=match_result.parsed_qty,
                    source_file=self.source_file,
                    imported_at=imported_at,
                )
                result.updates.append(record)
                result.updated += 1

                logger.info(
                    f"Updated stock for {match_result.normalized_sku}: "
                    f"{old_stock_doc} -> {new_stock_doc}"
                )

            except Exception as e:
                logger.error(f"Failed to update {match_result.normalized_sku}: {e}")
                result.errors += 1

        # Store brand distribution
        result.final_brand_distribution = brand_distribution

        return result

    def add_stock_movement(
        self,
        product_id: int,
        quantity: float,
        comment: str,
        imported_at: datetime,
    ) -> None:
        """Add a stock movement record for audit trail.

        This is optional - can be called after successful updates.
        """
        try:
            self.inventory_repo.add_movement(
                product_id=product_id,
                movement_type=models.MovementType.ADJUST,
                quantity=quantity,
                unit="pcs",
                source=self.source_name,
                comment=comment,
                created_by=None,  # System import
            )
            logger.debug(f"Added stock movement for product {product_id}")
        except Exception as e:
            logger.warning(f"Failed to add stock movement for {product_id}: {e}")