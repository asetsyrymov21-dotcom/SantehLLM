"""
Models for PDF enrichment pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional


class EnrichmentStatus(str, Enum):
    """Status of enrichment for a single product."""

    MATCHED = "matched"
    NOT_MATCHED = "not_matched"
    UPDATED = "updated"
    FAILED = "failed"
    SKIPPED = "skipped"


# =============================================================================
# PDF Dump Models - for saved PDF data (bootstrap layer)
# =============================================================================


@dataclass
class PdfPageDump:
    """Raw text dump from a single PDF page."""

    page_number: int
    raw_text: str
    skus_found: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "page_number": self.page_number,
            "raw_text": self.raw_text,
            "skus_found": self.skus_found,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PdfPageDump:
        """Create from dictionary."""
        return cls(
            page_number=data["page_number"],
            raw_text=data["raw_text"],
            skus_found=data.get("skus_found", []),
        )


@dataclass
class PdfTextDump:
    """Complete text dump from a PDF file."""

    pdf_path: str
    created_at: str
    page_count: int
    pages: list[PdfPageDump] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "pdf_path": self.pdf_path,
            "created_at": self.created_at,
            "page_count": self.page_count,
            "pages": [p.to_dict() for p in self.pages],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PdfTextDump:
        """Create from dictionary."""
        return cls(
            pdf_path=data["pdf_path"],
            created_at=data["created_at"],
            page_count=data["page_count"],
            pages=[PdfPageDump.from_dict(p) for p in data.get("pages", [])],
        )


@dataclass
class SkuIndex:
    """SKU index mapping SKU to candidate pages."""

    pdf_path: str
    created_at: str
    sku_to_pages: dict[str, list[int]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "pdf_path": self.pdf_path,
            "created_at": self.created_at,
            "sku_to_pages": self.sku_to_pages,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SkuIndex:
        """Create from dictionary."""
        return cls(
            pdf_path=data["pdf_path"],
            created_at=data["created_at"],
            sku_to_pages=data.get("sku_to_pages", {}),
        )

    def get_pages_for_sku(self, sku: str) -> list[int]:
        """Get candidate page numbers for a SKU."""
        # Try exact match first
        if sku in self.sku_to_pages:
            return self.sku_to_pages[sku]

        # Try case-insensitive match
        upper_sku = sku.upper()
        for key, pages in self.sku_to_pages.items():
            if key.upper() == upper_sku:
                return pages

        # Try without dashes
        no_dash = sku.replace("-", "")
        for key, pages in self.sku_to_pages.items():
            if key.replace("-", "") == no_dash:
                return pages

        return []


# =============================================================================
# Legacy Models - kept for compatibility
# =============================================================================


@dataclass
class PdfProductMatch:
    """Represents a product found in PDF catalog."""

    sku: str
    pdf_title: str
    pdf_subtitle: Optional[str] = None
    pdf_description: Optional[str] = None
    source_file: Optional[str] = None
    source_page: Optional[int] = None
    additional_attributes: dict[str, Any] = field(default_factory=dict)


@dataclass
class ProductEnrichmentRecord:
    """Record of enrichment attempt for a single product."""

    # Product identification
    product_id: int
    sku: str
    old_name: str
    old_description: Optional[str] = None

    # PDF match data
    pdf_match: Optional[PdfProductMatch] = None

    # Decision
    will_replace_name: bool = False
    will_update_description: bool = False
    replace_reason: Optional[str] = None

    # Status
    status: EnrichmentStatus = EnrichmentStatus.SKIPPED
    error_message: Optional[str] = None

    # Dry-run debug info
    candidate_pages: list[int] = field(default_factory=list)

    def to_report_row(self) -> dict[str, Any]:
        """Convert to dict for dry-run report."""
        return {
            "sku": self.sku,
            "old_name": (
                self.old_name[:80] + "..." if len(self.old_name) > 80 else self.old_name
            ),
            "pdf_name": (
                (
                    self.pdf_match.pdf_title[:80] + "..."
                    if len(self.pdf_match.pdf_title) > 80
                    else self.pdf_match.pdf_title
                )
                if self.pdf_match
                else None
            ),
            "will_replace_name": self.will_replace_name,
            "will_update_desc": self.will_update_description,
            "source_page": self.pdf_match.source_page if self.pdf_match else None,
            "source_file": self.pdf_match.source_file if self.pdf_match else None,
            "reason": self.replace_reason or self.status.value,
        }

    def to_detailed_report_row(self) -> dict[str, Any]:
        """Convert to dict with detailed dry-run info."""
        return {
            "sku": self.sku,
            "old_name": self.old_name,
            "candidate_pages": self.candidate_pages,
            "matched": self.pdf_match is not None,
            "source_page": self.pdf_match.source_page if self.pdf_match else None,
            "pdf_name": self.pdf_match.source_file if self.pdf_match else None,
            "will_replace_name": self.will_replace_name,
            "reason": self.replace_reason or self.status.value,
        }


@dataclass
class EnrichmentResult:
    """Result of enrichment process."""

    records: list[ProductEnrichmentRecord] = field(default_factory=list)
    total_processed: int = 0
    total_matched: int = 0
    total_not_matched: int = 0
    total_updated: int = 0
    total_failed: int = 0

    def add_record(self, record: ProductEnrichmentRecord) -> None:
        self.records.append(record)
        self.total_processed += 1

        if record.status == EnrichmentStatus.MATCHED:
            self.total_matched += 1
        elif record.status == EnrichmentStatus.NOT_MATCHED:
            self.total_not_matched += 1
        elif record.status == EnrichmentStatus.UPDATED:
            self.total_updated += 1
        elif record.status == EnrichmentStatus.FAILED:
            self.total_failed += 1


@dataclass
class EnrichmentSummary:
    """Summary of enrichment run."""

    mode: str  # "dry_run" or "apply"
    total_flagged: int = 0
    matched: int = 0
    not_matched: int = 0
    name_replacements_planned: int = 0
    description_updates_planned: int = 0
    updated_name: int = 0
    updated_description: int = 0
    cleared_needs_pdf_enrichment: int = 0
    failed: int = 0

    def print_dry_run(self) -> None:
        """Print dry-run summary."""
        print("\n" + "=" * 60)
        print("PDF ENRICHMENT DRY RUN SUMMARY")
        print("=" * 60)
        print(f"Total flagged products:    {self.total_flagged}")
        print(f"Matched in PDF:            {self.matched}")
        print(f"Not matched:               {self.not_matched}")
        print(f"Name replacements planned: {self.name_replacements_planned}")
        print(f"Description updates planned: {self.description_updates_planned}")
        print("=" * 60)
        print("\nNo database changes were made.")

    def print_apply(self) -> None:
        """Print apply summary."""
        print("\n" + "=" * 60)
        print("PDF ENRICHMENT APPLY SUMMARY")
        print("=" * 60)
        print(f"Total processed:           {self.total_flagged}")
        print(f"Matched in PDF:            {self.matched}")
        print(f"Updated name:              {self.updated_name}")
        print(f"Updated description:       {self.updated_description}")
        print(f"Cleared needs_pdf_enrichment: {self.cleared_needs_pdf_enrichment}")
        print(f"Not matched:               {self.not_matched}")
        print(f"Failed:                    {self.failed}")
        print("=" * 60)


@dataclass
class NameQualityAssessment:
    """Assessment of product name quality."""

    is_weak: bool = False
    is_sku_only: bool = False
    is_color_only: bool = False
    is_very_short: bool = False
    is_garbled: bool = False
    reasons: list[str] = field(default_factory=list)

    @property
    def needs_replacement(self) -> bool:
        """Check if name definitely needs replacement (aggressive mode)."""
        return (
            self.is_weak
            or self.is_sku_only
            or self.is_color_only
            or self.is_very_short
            or self.is_garbled
        )
