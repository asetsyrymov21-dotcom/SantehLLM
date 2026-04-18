"""
Main PDF Enrichment Service - Refactored for saved data.

Orchestrates the enrichment pipeline for flagged products.
Uses pre-built PDF dumps and indexes instead of live PDF scanning.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any, Optional

from sqlalchemy.orm import Session
from sqlalchemy import select

from app.db import models
from .models import (
    EnrichmentResult,
    EnrichmentStatus,
    EnrichmentSummary,
    PdfProductMatch,
    ProductEnrichmentRecord,
)
from .decision import ReplacementDecisionEngine
from .repository import SavedPdfRepository, MultiPdfRepository

logger = logging.getLogger(__name__)


class PdfEnrichmentService:
    """Service for enriching flagged products from PDF catalogs.

    Refactored architecture:
    - No live PDF scanning during enrichment
    - Uses pre-built PDF dumps and SKU indexes
    - Fast lookup via SavedPdfRepository
    """

    def __init__(
        self,
        session: Session,
        dump_paths: list[Path | str],
        index_paths: list[Path | str],
        mode: str = "conservative",
        pdf_names: Optional[list[str]] = None,
    ):
        self.session = session
        self.mode = mode

        self.repositories: list[SavedPdfRepository] = []
        for i, (dump, index) in enumerate(zip(dump_paths, index_paths)):
            name = pdf_names[i] if pdf_names and i < len(pdf_names) else None
            repo = SavedPdfRepository(dump, index, pdf_name=name)
            self.repositories.append(repo)

        self.multi_repo = MultiPdfRepository()
        for repo in self.repositories:
            self.multi_repo.add_repository(repo)

        self.decision_engine = ReplacementDecisionEngine()

        logger.info(f"PdfEnrichmentService initialized (mode={mode})")

    def load_data(self) -> None:
        """Load all saved PDF data."""
        logger.info("Loading saved PDF data...")
        for repo in self.repositories:
            repo.load()
        logger.info(f"Loaded {len(self.repositories)} repositories")

    def get_flagged_products(
        self,
        limit: Optional[int] = None,
        only_skus: Optional[set[str]] = None,
    ) -> list[models.Product]:
        stmt = select(models.Product).where(models.Product.attributes_json.isnot(None))
        products = self.session.scalars(stmt).all()

        flagged = []
        for product in products:
            attrs = product.attributes_json or {}

            if attrs.get("needs_pdf_enrichment") is not True:
                continue

            if not product.sku.startswith("G"):
                continue

            if only_skus and product.sku not in only_skus:
                continue

            flagged.append(product)

        flagged.sort(key=lambda p: p.sku)

        if limit:
            flagged = flagged[:limit]

        return flagged

    def _try_reference_fallback(
        self,
        repo: SavedPdfRepository,
        candidate_page_num: int,
        candidate_raw_text: str,
        sku: str,
    ) -> Optional[PdfProductMatch]:
        """Try overview/reference page -> detail page fallback."""
        from .extractor import (
            extract_candidate_from_page_text,
            extract_referenced_pages_for_sku,
            extract_referenced_pages_for_token,
            derive_reference_tokens,
        )

        referenced_pages = extract_referenced_pages_for_sku(candidate_raw_text, sku)
        logger.info("[SKU %s] refs from full SKU '%s': %s", sku, sku, referenced_pages)

        if not referenced_pages:
            derived_tokens = derive_reference_tokens(sku)
            logger.info("[SKU %s] derived tokens: %s", sku, derived_tokens)

            for token in derived_tokens:
                token_refs = extract_referenced_pages_for_token(
                    candidate_raw_text, token
                )
                logger.info("[SKU %s] refs from token '%s': %s", sku, token, token_refs)
                referenced_pages.extend(token_refs)

        seen = set()
        unique_pages = []
        for page_no in referenced_pages:
            if page_no not in seen:
                seen.add(page_no)
                unique_pages.append(page_no)

        logger.info("[SKU %s] unique refs: %s", sku, unique_pages)

        if not unique_pages:
            logger.info("[SKU %s] FALLBACK FAIL: no ref pages", sku)
            return None

        for detail_page_num in unique_pages:
            detail_dump = repo.get_page(detail_page_num)
            if not detail_dump or not detail_dump.raw_text:
                logger.info("[SKU %s] detail page %s: NO TEXT", sku, detail_page_num)
                continue

            logger.info(
                "[SKU %s] trying detail page %s (len=%s)",
                sku,
                detail_page_num,
                len(detail_dump.raw_text),
            )

            match = extract_candidate_from_page_text(
                sku=sku,
                page_number=detail_page_num,
                raw_text=detail_dump.raw_text,
                pdf_name=repo.pdf_name,
            )

            if match:
                ...
                return match

            logger.info("[SKU %s] detail page %s: no match", sku, detail_page_num)

        logger.info("[SKU %s] FALLBACK FAIL: all detail pages exhausted", sku)
        return None

    def _find_sku_in_saved_data(self, sku: str) -> Optional[PdfProductMatch]:
        """Find SKU in saved PDF data (replaces live PDF scanning)."""
        from .extractor import extract_candidate_from_page_text

        normalized_sku = sku.upper().strip()

        for repo in self.repositories:
            candidate_pages = repo.get_candidate_pages(normalized_sku)
            if not candidate_pages:
                continue

            logger.info(
                "[SKU %s] repo=%s candidate_pages=%s",
                normalized_sku,
                repo.pdf_name,
                candidate_pages,
            )

            for page_num in candidate_pages:
                page_dump = repo.get_page(page_num)
                if not page_dump or not page_dump.raw_text:
                    logger.info("[SKU %s] page %s: NO TEXT", normalized_sku, page_num)
                    continue

                logger.info(
                    "[SKU %s] trying candidate page %s (len=%s)",
                    normalized_sku,
                    page_num,
                    len(page_dump.raw_text),
                )

                match = extract_candidate_from_page_text(
                    sku=normalized_sku,
                    page_number=page_num,
                    raw_text=page_dump.raw_text,
                    pdf_name=repo.pdf_name,
                )

                if match:
                    logger.info(
                        "[SKU %s] DIRECT MATCH on page %s: title='%s'",
                        normalized_sku,
                        page_num,
                        match.pdf_title[:80] if match.pdf_title else "NONE",
                    )
                    match.additional_attributes = match.additional_attributes or {}
                    match.additional_attributes["source_candidate_page"] = page_num
                    match.additional_attributes["resolved_detail_page"] = page_num
                    match.additional_attributes["match_strategy"] = "direct_detail"
                    return match

                logger.info(
                    "[SKU %s] direct on page %s: NO MATCH -> fallback",
                    normalized_sku,
                    page_num,
                )

                fallback_match = self._try_reference_fallback(
                    repo=repo,
                    candidate_page_num=page_num,
                    candidate_raw_text=page_dump.raw_text,
                    sku=normalized_sku,
                )
                if fallback_match:
                    return fallback_match

        return None

    def _process_product_dry_run(
        self, product: models.Product, verbose: bool
    ) -> ProductEnrichmentRecord:
        """Process a single product in dry-run mode."""
        record = ProductEnrichmentRecord(
            product_id=product.id,
            sku=product.sku,
            old_name=product.name or "",
            old_description=product.description,
        )

        all_candidates = []
        for repo in self.repositories:
            pages = repo.get_candidate_pages(product.sku)
            all_candidates.extend(pages)
        record.candidate_pages = sorted(set(all_candidates))

        if verbose:
            logger.info(
                "[SKU %s] aggregated candidate pages: %s",
                product.sku,
                record.candidate_pages,
            )

        pdf_match = self._find_sku_in_saved_data(product.sku)

        if not pdf_match:
            record.status = EnrichmentStatus.NOT_MATCHED
            record.replace_reason = "SKU not found in PDF catalogs"
            return record

        record.pdf_match = pdf_match
        record.status = EnrichmentStatus.MATCHED

        will_replace, replace_reason = self.decision_engine.decide_name_replacement(
            product.name or "", pdf_match, mode=self.mode
        )
        record.will_replace_name = will_replace
        record.replace_reason = replace_reason

        will_update, _ = self.decision_engine.decide_description_update(
            product.description, pdf_match
        )
        record.will_update_description = will_update

        return record

    def run_dry_run(
        self, limit: Optional[int] = None, verbose: bool = False
    ) -> EnrichmentResult:
        """Run enrichment in dry-run mode (no DB changes)."""
        logger.info("=" * 60)
        logger.info(f"PDF ENRICHMENT DRY-RUN (limit={limit}, mode={self.mode})")
        logger.info("=" * 60)

        # Load saved data (no live PDF scanning)
        self.load_data()

        flagged_products = self.get_flagged_products(
            limit=limit,
            only_skus={"G2007-3", "G2007-9", "G30701-3"},
        )
        logger.info(f"Found {len(flagged_products)} flagged products")

        result = EnrichmentResult()

        for i, product in enumerate(flagged_products, 1):
            logger.info(
                f"\n--- [{i}/{len(flagged_products)}] Processing SKU: {product.sku} ---"
            )

            try:
                record = self._process_product_dry_run(product, verbose)
                result.add_record(record)
            except Exception as e:
                logger.error(f"Error processing {product.sku}: {e}")
                record = ProductEnrichmentRecord(
                    product_id=product.id,
                    sku=product.sku,
                    old_name=product.name or "",
                    old_description=product.description,
                    status=EnrichmentStatus.FAILED,
                    error_message=str(e),
                )
                result.add_record(record)

        logger.info(f"\n{'=' * 60}")
        logger.info(f"DRY-RUN COMPLETE: {result.total_processed} products")
        logger.info("=" * 60)

        return result

    def _process_product_apply(
        self, product: models.Product, verbose: bool
    ) -> ProductEnrichmentRecord:
        """Process a single product and apply changes."""
        # First do dry-run analysis
        record = self._process_product_dry_run(product, verbose)

        # If not matched or failed, don't apply anything
        if record.status in (EnrichmentStatus.NOT_MATCHED, EnrichmentStatus.FAILED):
            return record

        # Apply name replacement if approved
        if record.will_replace_name and record.pdf_match:
            product.name = record.pdf_match.pdf_title
            record.status = EnrichmentStatus.UPDATED
            logger.info(f"[SKU {product.sku}] Applied name change")

        # Apply description update if approved
        if record.will_update_description and record.pdf_match:
            new_description = record.pdf_match.pdf_description
            if new_description:
                if product.description:
                    product.description = (
                        f"{product.description}\n\nPDF Catalog Data:\n{new_description}"
                    )
                else:
                    product.description = new_description
                record.status = EnrichmentStatus.UPDATED
                logger.info(f"[SKU {product.sku}] Applied description update")

        # Update attributes
        attrs = product.attributes_json or {}
        if record.pdf_match:
            if "pdf_enrichment_sources" not in attrs:
                attrs["pdf_enrichment_sources"] = []

            source_info = {
                "source_file": record.pdf_match.source_file,
                "source_page": record.pdf_match.source_page,
                "enriched_at": str(__import__("datetime").datetime.utcnow()),
            }
            attrs["pdf_enrichment_sources"].append(source_info)

            should_clear = self.decision_engine.should_clear_enrichment_flag(
                record.old_name, product.name, record.pdf_match
            )

            if should_clear:
                attrs["needs_pdf_enrichment"] = False
                attrs["pdf_enrichment_completed_at"] = str(
                    __import__("datetime").datetime.utcnow()
                )
                logger.info(f"[SKU {product.sku}] Cleared needs_pdf_enrichment flag")

        product.attributes_json = attrs
        self.session.add(product)

        return record

    def run_apply(
        self, limit: Optional[int] = None, verbose: bool = False
    ) -> EnrichmentResult:
        """Run enrichment and apply changes to database."""
        logger.info("=" * 60)
        logger.info(f"PDF ENRICHMENT APPLY (limit={limit}, mode={self.mode})")
        logger.info("=" * 60)

        self.load_data()

        flagged_products = self.get_flagged_products(limit)
        logger.info(f"Found {len(flagged_products)} flagged products")

        result = EnrichmentResult()

        for i, product in enumerate(flagged_products, 1):
            logger.info(
                f"\n--- [{i}/{len(flagged_products)}] Processing SKU: {product.sku} ---"
            )

            try:
                record = self._process_product_apply(product, verbose)
                result.add_record(record)
            except Exception as e:
                logger.error(f"Error applying changes to {product.sku}: {e}")
                record = ProductEnrichmentRecord(
                    product_id=product.id,
                    sku=product.sku,
                    old_name=product.name or "",
                    old_description=product.description,
                    status=EnrichmentStatus.FAILED,
                    error_message=str(e),
                )
                result.add_record(record)

        try:
            self.session.commit()
            logger.info("Database changes committed successfully")
        except Exception as e:
            self.session.rollback()
            logger.error(f"Failed to commit changes: {e}")
            raise

        logger.info(f"\n{'=' * 60}")
        logger.info(f"APPLY COMPLETE: {result.total_processed} products")
        logger.info("=" * 60)

        return result

    def build_summary(self, result: EnrichmentResult, mode: str) -> EnrichmentSummary:
        """Build summary from enrichment result."""
        summary = EnrichmentSummary(mode=mode)

        summary.total_flagged = result.total_processed
        summary.matched = result.total_matched
        summary.not_matched = result.total_not_matched
        summary.failed = result.total_failed

        for record in result.records:
            if record.will_replace_name:
                summary.name_replacements_planned += 1
            if record.will_update_description:
                summary.description_updates_planned += 1

            if mode == "apply":
                if record.status == EnrichmentStatus.UPDATED:
                    if record.will_replace_name:
                        summary.updated_name += 1
                    if record.will_update_description:
                        summary.updated_description += 1

        return summary

    def print_dry_run_report(self, result: EnrichmentResult) -> None:
        """Print detailed dry-run report."""
        summary = self.build_summary(result, "dry_run")
        summary.print_dry_run()

        # Print detailed table
        print("\n" + "=" * 100)
        print("DETAILED DRY-RUN REPORT")
        print("=" * 100)
        print(
            f"{'SKU':<15} {'Candidate Pages':<20} {'Old Name':<30} {'PDF Name':<30} {'Replace':<8}"
        )
        print("-" * 100)

        for record in result.records:
            if record.pdf_match:
                old_name = (
                    record.old_name[:27] + "..."
                    if len(record.old_name) > 30
                    else record.old_name
                )
                pdf_name = (
                    record.pdf_match.pdf_title[:27] + "..."
                    if len(record.pdf_match.pdf_title or "") > 30
                    else (record.pdf_match.pdf_title or "")
                )
                pages_str = (
                    str(record.candidate_pages[:3])[:18]
                    if record.candidate_pages
                    else "[]"
                )
                print(
                    f"{record.sku:<15} {pages_str:<20} {old_name:<30} {pdf_name:<30} {str(record.will_replace_name):<8}"
                )
            else:
                old_name = (
                    record.old_name[:27] + "..."
                    if len(record.old_name) > 30
                    else record.old_name
                )
                pages_str = (
                    str(record.candidate_pages[:3])[:18]
                    if record.candidate_pages
                    else "[]"
                )
                print(
                    f"{record.sku:<15} {pages_str:<20} {old_name:<30} {'N/A':<30} {'N/A':<8}"
                )

        print("=" * 100)

    def print_apply_report(self, result: EnrichmentResult) -> None:
        """Print detailed apply report."""
        summary = self.build_summary(result, "apply")
        summary.print_apply()

        updated_records = [
            r for r in result.records if r.status == EnrichmentStatus.UPDATED
        ]

        if updated_records:
            print("\n" + "=" * 100)
            print("UPDATED PRODUCTS")
            print("=" * 100)
            print(f"{'SKU':<15} {'Page':<8} {'Old Name':<35} {'New Name':<35}")
            print("-" * 100)

            for record in updated_records:
                old_name = (
                    record.old_name[:32] + "..."
                    if len(record.old_name) > 35
                    else record.old_name
                )
                new_name = (
                    record.pdf_match.pdf_title if record.pdf_match else record.old_name
                )
                new_name = new_name[:32] + "..." if len(new_name) > 35 else new_name
                page = f"p{record.pdf_match.source_page}" if record.pdf_match else "N/A"
                print(f"{record.sku:<15} {page:<8} {old_name:<35} {new_name:<35}")

            print("=" * 100)
