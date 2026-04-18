"""Stock import matcher with detailed dry-run reporting.

Handles SKU matching, duplicate detection, and brand filtering (FRAP, GAPPO).
"""

from __future__ import annotations

import csv
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from sqlalchemy.orm import Session

from app.repositories.product import ProductRepository
from app.utils.sku_utils import normalize_sku, derive_brand_from_sku, is_frap_sku
from app.utils.stock_parser import parse_stock_value, ParsedStockValue
from .excel_parser import ExcelStockRow

import re

logger = logging.getLogger(__name__)


@dataclass
class MatchResult:
    """Result of matching a single row."""

    row_index: int
    raw_sku: Optional[str]
    normalized_sku: Optional[str]
    raw_qty: any
    parsed_qty: ParsedStockValue
    product_id: Optional[int]
    match_status: str  # "matched", "unmatched", "skipped_non_frap", "duplicate", "invalid_sku", "invalid_qty", "empty_qty"
    brand_derived: Optional[str]
    sheet_name: Optional[str] = None  # Source sheet name
    notes: list[str] = field(default_factory=list)

    def to_report_dict(self) -> dict:
        """Convert to dict for reporting with correct field mapping."""
        return {
            "sku_raw": self.raw_sku if self.raw_sku is not None else "",
            "sku_normalized": (
                self.normalized_sku if self.normalized_sku is not None else ""
            ),
            "sheet_name": self.sheet_name if self.sheet_name is not None else "",
            "source_row": self.row_index,
            "qty_raw": str(self.raw_qty) if self.raw_qty is not None else "",
            "qty_parsed": self.parsed_qty.stock_label if self.parsed_qty else "",
            "qty_status": self.parsed_qty.parse_status if self.parsed_qty else "",
            "product_id": self.product_id if self.product_id is not None else "",
            "brand": self.brand_derived if self.brand_derived is not None else "",
            "status": self.match_status,
            "notes": "; ".join(self.notes) if self.notes else "",
        }


@dataclass
class UnmatchedSkuReport:
    """Detailed report for unmatched SKUs."""

    unmatched_results: list[MatchResult]
    generated_at: datetime

    def to_csv_v2(self, filepath: Path) -> Path:
        """Export unmatched SKUs to CSV using to_report_dict() for consistent field mapping."""
        filepath.parent.mkdir(parents=True, exist_ok=True)

        if self.unmatched_results:
            fieldnames = list(self.unmatched_results[0].to_report_dict().keys())
        else:
            fieldnames = [
                "row",
                "sku_raw",
                "sku_normalized",
                "qty_raw",
                "qty_parsed",
                "qty_status",
                "product_id",
                "brand",
                "sheet_name",
                "status",
                "notes",
            ]

        with open(filepath, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()

            for r in self.unmatched_results:
                row_dict = r.to_report_dict()
                row_dict = {
                    k: str(v) if v is not None else "" for k, v in row_dict.items()
                }
                writer.writerow(row_dict)

        return filepath

    def analyze(self) -> dict:
        """Analyze unmatched SKUs by problem type."""
        analysis = {
            "total_unmatched": len(self.unmatched_results),
            "by_type": {
                "truly_missing": [],  # SKU looks valid but not in DB
                "normalization_issue": [],  # Possible normalize mismatch
                "format_issue": [],  # SKU format looks wrong
                "empty_or_invalid": [],  # Empty/very short SKU
            },
        }

        for r in self.unmatched_results:
            sku = r.normalized_sku or ""
            raw = r.raw_sku or ""

            # Categorize by pattern
            if not sku or len(sku) < 3:
                analysis["by_type"]["empty_or_invalid"].append(r)
            elif sku != raw and raw and len(raw) > len(sku):
                # Normalization changed SKU significantly
                analysis["by_type"]["normalization_issue"].append(r)
            elif len(sku) >= 5 and (sku[0].isalpha() or sku[0].isdigit()):
                # Looks like valid SKU format
                analysis["by_type"]["truly_missing"].append(r)
            else:
                analysis["by_type"]["format_issue"].append(r)

        return analysis

    def print_analysis(self, max_examples: int = 5) -> None:
        """Print detailed analysis to stdout."""
        analysis = self.analyze()

        print("\n" + "=" * 70)
        print("UNMATCHED SKU ANALYSIS")
        print("=" * 70)
        print(f"Total unmatched: {analysis['total_unmatched']}")
        print()

        # Truly missing
        missing = analysis["by_type"]["truly_missing"]
        print(f"1. TRULY MISSING IN CATALOG ({len(missing)} items)")
        print("   These SKUs look valid but don't exist in database")
        print("   Recommendation: Import these products to catalog")
        print("-" * 70)
        for r in missing[:max_examples]:
            print(
                f"   {r.normalized_sku:<15} | row {r.row_index:<4} | raw: {r.raw_sku}"
            )
        if len(missing) > max_examples:
            print(f"   ... and {len(missing) - max_examples} more")
        print()

        # Normalization issues
        norm = analysis["by_type"]["normalization_issue"]
        print(f"2. POSSIBLE NORMALIZATION MISMATCH ({len(norm)} items)")
        print("   Raw SKU differs significantly from normalized")
        print("   Recommendation: Review SKU normalization rules")
        print("-" * 70)
        for r in norm[:max_examples]:
            print(f"   raw: {r.raw_sku:<20} -> norm: {r.normalized_sku}")
        if len(norm) > max_examples:
            print(f"   ... and {len(norm) - max_examples} more")
        print()

        # Format issues
        fmt = analysis["by_type"]["format_issue"]
        print(f"3. FORMAT ISSUES ({len(fmt)} items)")
        print("   SKU format looks suspicious")
        print("   Recommendation: Check source data quality")
        print("-" * 70)
        for r in fmt[:max_examples]:
            print(f"   {r.raw_sku!r:<25} | norm: {r.normalized_sku!r}")
        if len(fmt) > max_examples:
            print(f"   ... and {len(fmt) - max_examples} more")
        print()

        # Empty/invalid
        empty = analysis["by_type"]["empty_or_invalid"]
        print(f"4. EMPTY OR INVALID ({len(empty)} items)")
        print("   SKU is empty or too short")
        print("-" * 70)
        for r in empty[: min(max_examples, 3)]:
            print(f"   row {r.row_index}: raw={r.raw_sku!r}, norm={r.normalized_sku!r}")
        print("=" * 70)


@dataclass
class StockMatchReport:
    """Complete report from dry-run matching."""

    # Source stats
    total_rows_scanned: int
    non_empty_rows: int
    rows_with_article: int
    rows_with_valid_normalized_sku: int

    # Brand filtering
    frap_candidate_rows: int
    gappo_candidate_rows: int
    skipped_unsupported_brand: int
    skipped_non_frap: int  # Deprecated, kept for compatibility

    # SKU quality
    duplicate_sku_in_source: int
    skipped_invalid_sku: int

    # Matching
    matched_in_db: int
    unmatched_in_db: int

    # Quantity parsing
    invalid_qty: int  # Excel errors (#REF!, #N/A, etc.)
    empty_qty_as_zero: int  # Empty qty treated as 0 (valid, not skipped)

    # Ready for update
    planned_updates: int

    # Detailed results
    results: list[MatchResult] = field(default_factory=list)

    # Duplicate tracking
    duplicate_skus: dict[str, list[int]] = field(
        default_factory=dict
    )  # sku -> row indices

    def print_report(self) -> None:
        """Print formatted report to stdout."""
        total_accounted = (
            self.skipped_unsupported_brand
            + self.duplicate_sku_in_source
            + self.skipped_invalid_sku
            + self.invalid_qty
            + self.unmatched_in_db
            + self.planned_updates
        )
        delta = self.total_rows_scanned - total_accounted

        print("\n" + "=" * 60)
        print("STOCK IMPORT DRY RUN (FRAP + GAPPO)")
        print("=" * 60)
        print(f"Rows scanned from source: {self.total_rows_scanned}")
        print("-" * 60)
        print(f"  Processed FRAP candidates:  {self.frap_candidate_rows}")
        print(f"  Processed GAPPO candidates: {self.gappo_candidate_rows}")
        print(f"  Skipped unsupported brand:  {self.skipped_unsupported_brand}")
        print(f"  Skipped duplicate SKU:      {self.duplicate_sku_in_source}")
        print(f"  Skipped invalid SKU:        {self.skipped_invalid_sku}")
        print(f"  Skipped invalid qty:        {self.invalid_qty}")
        print(f"  Empty qty as zero:          {self.empty_qty_as_zero}  [INFO]")
        print("-" * 60)
        print(f"  Skipped no product:         {self.unmatched_in_db}")
        print(f"  Updated:                    {self.planned_updates}")
        print("-" * 60)
        print(f"  TOTAL ACCOUNTED:            {total_accounted}")
        print(f"  DELTA:                      {delta}")
        print("=" * 60)

    def print_detailed_report(self, max_rows: int = 50) -> None:
        """Print detailed row-by-row report."""
        if not self.results:
            print("\nNo rows to display in detailed report.")
            return

        print("\n--- DETAILED REPORT ---")
        print(
            f"{'Row':<5} {'SKU Raw':<15} {'SKU Norm':<12} {'Qty Raw':<10} {'Qty Parsed':<10} {'Product ID':<10} {'Status':<15} {'Notes'}"
        )
        print("-" * 120)

        for r in self.results[:max_rows]:
            sku_raw = (r.raw_sku or "")[:14]
            sku_norm = (r.normalized_sku or "")[:11]
            qty_raw = str(r.raw_qty or "")[:9]
            qty_parsed = r.parsed_qty.stock_label[:9]
            prod_id = str(r.product_id or "-")[:9]
            status = r.match_status[:14]
            notes = "; ".join(r.notes)[:30] if r.notes else ""

            print(
                f"{r.row_index:<5} {sku_raw:<15} {sku_norm:<12} {qty_raw:<10} {qty_parsed:<10} {prod_id:<10} {status:<15} {notes}"
            )

        if len(self.results) > max_rows:
            print(f"... and {len(self.results) - max_rows} more rows")

    def print_duplicate_warning(self) -> None:
        """Print warning about duplicate SKUs."""
        if not self.duplicate_skus:
            return

        print("\n--- DUPLICATE SKU WARNING ---")
        print("The following SKUs appear multiple times in source:")
        for sku, rows in sorted(self.duplicate_skus.items()):
            print(f"  SKU '{sku}': rows {rows}")
        print(
            "\nIn commit mode, duplicate SKUs will be SKIPPED until merge policy is defined."
        )
        print("------------------------------")

    def get_unmatched_report(self) -> UnmatchedSkuReport:
        """Generate report for unmatched SKUs."""
        unmatched = [r for r in self.results if r.match_status == "unmatched"]
        return UnmatchedSkuReport(
            unmatched_results=unmatched, generated_at=datetime.utcnow()
        )

    def export_unmatched_to_csv(self, filepath: Path) -> Path:
        """Export unmatched SKUs to CSV file."""
        report = self.get_unmatched_report()
        return report.to_csv_v2(filepath)


class StockMatcher:
    """Matches stock rows against database products."""

    # Supported brands for stock import
    SUPPORTED_BRANDS = {"FRAP", "GAPPO"}

    def __init__(self, session: Session, brand_filter: Optional[set[str]] = None):
        """
        Args:
            session: Database session
            brand_filter: Set of brands to process (None = FRAP + GAPPO)
        """
        self.session = session
        self.product_repo = ProductRepository(session)
        self.brand_filter = (
            brand_filter if brand_filter is not None else self.SUPPORTED_BRANDS
        )

    def match_rows(self, rows: list[ExcelStockRow]) -> StockMatchReport:
        """Match all rows against database and build report.

        Args:
            rows: Parsed Excel rows

        Returns:
            StockMatchReport with complete analysis
        """
        report = StockMatchReport(
            total_rows_scanned=0,  # Will be set from parser result
            non_empty_rows=len(rows),
            rows_with_article=0,
            rows_with_valid_normalized_sku=0,
            frap_candidate_rows=0,
            gappo_candidate_rows=0,
            skipped_unsupported_brand=0,
            skipped_non_frap=0,
            duplicate_sku_in_source=0,
            skipped_invalid_sku=0,
            matched_in_db=0,
            unmatched_in_db=0,
            invalid_qty=0,
            empty_qty_as_zero=0,
            planned_updates=0,
        )

        seen_skus: dict[str, int] = {}  # sku -> first row index

        for row in rows:
            result = self._match_single_row(row)

            if result.brand_derived == "FRAP":
                report.frap_candidate_rows += 1
            elif result.brand_derived == "GAPPO":
                report.gappo_candidate_rows += 1

            # Count rows with article
            if row.raw_article:
                report.rows_with_article += 1

            # Duplicate detection must happen BEFORE status counters
            if result.normalized_sku:
                report.rows_with_valid_normalized_sku += 1

                if result.normalized_sku in seen_skus:
                    if result.normalized_sku not in report.duplicate_skus:
                        report.duplicate_skus[result.normalized_sku] = [
                            seen_skus[result.normalized_sku]
                        ]
                    report.duplicate_skus[result.normalized_sku].append(row.row_index)

                    # Reclassify repeated rows as duplicate final status
                    result.match_status = "duplicate"
                    result.product_id = None
                    result.notes.append("Duplicate SKU in source")
                else:
                    seen_skus[result.normalized_sku] = row.row_index

            report.results.append(result)

            # Count by final status (mutually exclusive)
            if result.match_status == "unsupported_brand":
                report.skipped_unsupported_brand += 1
            elif result.match_status == "skipped_non_frap":
                report.skipped_unsupported_brand += 1
                report.skipped_non_frap += 1
            elif result.match_status == "invalid_sku":
                report.skipped_invalid_sku += 1
            elif result.match_status == "invalid_qty":
                report.invalid_qty += 1
            elif result.match_status == "duplicate":
                report.duplicate_sku_in_source += 1
            elif result.match_status == "unmatched":
                report.unmatched_in_db += 1
                if result.parsed_qty.parse_status == "empty":
                    report.empty_qty_as_zero += 1
            elif result.match_status == "matched":
                report.matched_in_db += 1
                report.planned_updates += 1
                if result.parsed_qty.parse_status == "empty":
                    report.empty_qty_as_zero += 1

        return report

    def _match_single_row(self, row: ExcelStockRow) -> MatchResult:
        """Match a single row against database."""
        notes: list[str] = []

        # Step 1: Normalize SKU
        normalized_sku = normalize_sku(row.raw_article)

        if not normalized_sku:
            return MatchResult(
                row_index=row.row_index,
                raw_sku=row.raw_article,
                normalized_sku=None,
                raw_qty=row.raw_quantity,
                parsed_qty=parse_stock_value(None),
                product_id=None,
                match_status="invalid_sku",
                brand_derived=None,
                sheet_name=row.sheet_name,
                notes=["Empty or invalid article/SKU"],
            )

        # Step 2: Derive brand from SKU
        brand = derive_brand_from_sku(normalized_sku)

        # Step 3: Check brand filter - FRAP and GAPPO are supported
        if brand not in self.brand_filter:
            return MatchResult(
                row_index=row.row_index,
                raw_sku=row.raw_article,
                normalized_sku=normalized_sku,
                raw_qty=row.raw_quantity,
                parsed_qty=parse_stock_value(row.raw_quantity),
                product_id=None,
                match_status="unsupported_brand",
                brand_derived=brand,
                sheet_name=row.sheet_name,
                notes=[f"Brand '{brand}' not in supported brands: {self.brand_filter}"],
            )

        # Step 4: Parse quantity
        parsed_qty = parse_stock_value(row.raw_quantity)

        if parsed_qty.parse_status == "invalid":
            return MatchResult(
                row_index=row.row_index,
                raw_sku=row.raw_article,
                normalized_sku=normalized_sku,
                raw_qty=row.raw_quantity,
                parsed_qty=parsed_qty,
                product_id=None,
                match_status="invalid_qty",
                brand_derived=brand,
                sheet_name=row.sheet_name,
                notes=[f"Invalid quantity (Excel error): {parsed_qty.raw_value}"],
            )

        if parsed_qty.parse_status == "empty":
            logger.debug(
                f"Row {row.row_index}: empty quantity interpreted as 0 for SKU {normalized_sku}"
            )

        # Step 5: Lookup product in DB
        lookup_candidates = [normalized_sku]
        lookup_candidates.extend(
            [
                normalized_sku.replace(".", ""),
                normalized_sku.replace("-", ""),
                normalized_sku.replace(" ", ""),
                normalized_sku.replace(".", "-"),
                normalized_sku.replace(".", "").replace("-", "").replace(" ", ""),
            ]
        )

        # Special fallback:
        # F823 -> F82-3
        # F825 -> F82-5
        # G453 -> G45-3
        m = re.match(r"^([A-Z])(\d{2,})(\d)$", normalized_sku)
        if m:
            prefix, body, last_digit = m.groups()
            lookup_candidates.append(f"{prefix}{body}-{last_digit}")

        # dedupe candidates, preserve order
        seen = set()
        deduped_candidates = []
        for candidate in lookup_candidates:
            if candidate and candidate not in seen:
                seen.add(candidate)
                deduped_candidates.append(candidate)

        product = None
        matched_sku_variant = None

        for candidate in deduped_candidates:
            product = self.product_repo.get_by_sku(candidate)
            if product:
                matched_sku_variant = candidate
                break

        if not product:
            return MatchResult(
                row_index=row.row_index,
                raw_sku=row.raw_article,
                normalized_sku=normalized_sku,
                raw_qty=row.raw_quantity,
                parsed_qty=parsed_qty,
                product_id=None,
                match_status="unmatched",
                brand_derived=brand,
                sheet_name=row.sheet_name,
                notes=[f"Product not found in database. Tried: {deduped_candidates}"],
            )

        if matched_sku_variant != normalized_sku:
            notes.append(
                f"Matched via fallback SKU variant: '{normalized_sku}' -> '{matched_sku_variant}'"
            )

        # Step 6: Check for conflicts (brand mismatch)
        if product.brand and product.brand != brand:
            notes.append(f"Brand conflict: DB='{product.brand}', Derived='{brand}'")

        return MatchResult(
            row_index=row.row_index,
            raw_sku=row.raw_article,
            normalized_sku=normalized_sku,
            raw_qty=row.raw_quantity,
            parsed_qty=parsed_qty,
            product_id=product.id,
            match_status="matched",
            brand_derived=brand,
            sheet_name=row.sheet_name,
            notes=notes,
        )

    def get_duplicate_sku_list(self, report: StockMatchReport) -> list[str]:
        """Get list of SKUs that are duplicated in source."""
        return list(report.duplicate_skus.keys())
