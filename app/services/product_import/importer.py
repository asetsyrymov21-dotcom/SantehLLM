"""
Main product importer with dry-run support and conflict resolution.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from app.db import models
from app.repositories.product import ProductRepository
from app.schemas.product import ProductCreate, ProductUpdate
from .normalizer import build_product_payload, normalize_text_for_comparison
from .dedup import ProductIdentity, deduplicate_items_locally
from .finalize_service import finalize_import
from app.services.post_import.reporting_service import run_post_import_summary

logger = logging.getLogger(__name__)


def _is_suspicious_product_name(name: str | None) -> bool:
    if not name:
        return True

    text = re.sub(r"\s+", " ", name).strip()
    text_lower = text.lower()

    if len(text) < 3:
        return True

    if len(text) > 120:
        return True

    bad_markers = [
        "каталог",
        "новинки",
        "стр.",
        "page",
        "www.",
        "http",
    ]
    if any(marker in text_lower for marker in bad_markers):
        return True

    bad_garbled_markers = ["╤", "Ё", "Є", "√", "№", "ё"]
    garbled_hits = sum(text.count(ch) for ch in bad_garbled_markers)
    if garbled_hits >= 3:
        return True

    sku_hits = re.findall(
        r"\b[A-Z]{1,3}\d{2,5}(?:-\d{1,3}[A-Z0-9]?)?\b",
        text,
        flags=re.IGNORECASE,
    )
    if len(sku_hits) >= 3:
        return True

    digits_count = len(re.findall(r"\d", text))
    if digits_count > 20:
        return True

    return False


def _should_replace_product_name(old_name: str | None, new_name: str | None) -> bool:
    if not new_name:
        return False

    if _is_suspicious_product_name(new_name):
        return False

    if not old_name:
        return True

    if _is_suspicious_product_name(old_name):
        return True

    old_clean = re.sub(r"\s+", " ", old_name).strip()
    new_clean = re.sub(r"\s+", " ", new_name).strip()

    if new_clean == old_clean:
        return False

    if len(new_clean) > len(old_clean):
        return True

    return False


def _classify_name_issue(
    old_name: str | None,
    new_name: str | None,
    sku: str | None,
) -> str | None:
    old_clean = re.sub(r"\s+", " ", (old_name or "")).strip()
    new_clean = re.sub(r"\s+", " ", (new_name or "")).strip()
    sku_clean = (sku or "").strip()

    if not new_clean or old_clean == new_clean:
        return None

    if _is_suspicious_product_name(old_clean):
        return "historical_db_damage"

    if (
        sku_clean
        and old_clean
        and sku_clean not in old_clean
        and sku_clean in new_clean
    ):
        return "historical_db_damage"

    old_lower = old_clean.lower()
    new_lower = new_clean.lower()

    generic_tail_markers = {
        "душевая система",
        "гигиенический душ",
        "смеситель для раковины",
        "смеситель для ванны",
        "смеситель для биде",
    }

    if any(marker in old_lower for marker in generic_tail_markers):
        if len(new_clean) >= len(old_clean) + 8 and new_lower != old_lower:
            return "historical_db_damage"

    if old_clean and len(old_clean) < max(10, int(len(new_clean) * 0.7)):
        return "name_change_needs_review"

    return None


def _ensure_result_buckets(result: ImportResult) -> None:
    if result.changed_rows is None:
        result.changed_rows = []

    if result.suspicious_pages is None:
        result.suspicious_pages = {}


def _mark_suspicious_page(
    result: ImportResult,
    page: int | None,
    sku: str | None,
    reason: str,
) -> None:
    if page is None:
        return

    _ensure_result_buckets(result)

    bucket = result.suspicious_pages.setdefault(
        page,
        {
            "reasons": set(),
            "skus": set(),
            "updated": 0,
            "created": 0,
            "skipped": 0,
        },
    )
    bucket["reasons"].add(reason)
    if sku:
        bucket["skus"].add(sku)


@dataclass
class ImportResult:
    """Result of product import operation."""

    total: int = 0
    created: int = 0
    updated: int = 0
    skipped: int = 0
    errors: int = 0
    dry_run: bool = True
    details: list[dict] = field(default_factory=list)
    changed_rows: list[dict] = field(default_factory=list)
    suspicious_pages: dict[int, dict[str, Any]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "total": self.total,
            "created": self.created,
            "updated": self.updated,
            "skipped": self.skipped,
            "errors": self.errors,
            "dry_run": self.dry_run,
        }


class ProductImporter:
    """
    Safe product importer with deduplication and dry-run support.
    """

    def __init__(self, session: Session):
        self.session = session
        self.repo = ProductRepository(session)
        self.result = ImportResult()

    def import_products(
        self, items: list[dict[str, Any]], dry_run: bool = True
    ) -> ImportResult:
        """
        Import products from extracted items.

        Args:
            items: Raw product dicts from PDF extraction
            dry_run: If True, only simulate without DB writes

        Returns:
            ImportResult with statistics
        """
        self.result = ImportResult(dry_run=dry_run)

        if not items:
            logger.warning("No items to import")
            return self.result

        logger.info(f"Starting import of {len(items)} items (dry_run={dry_run})")

        # Step 1: Local deduplication
        unique_identities = deduplicate_items_locally(items)
        deduped_count = len(unique_identities)
        logger.info(f"After deduplication: {deduped_count} unique items")

        self.result.total = deduped_count

        # Step 2: Process each unique item
        for identity in unique_identities:
            try:
                self._process_identity(identity)
            except Exception as e:
                logger.error(f"Failed to process {identity.name}: {e}")
                self.result.errors += 1
                self.result.details.append(
                    {
                        "name": identity.name,
                        "sku": identity.sku,
                        "action": "error",
                        "error": str(e),
                    }
                )

        # Step 3: Apply brand overrides, then commit
        brand_result = None
        if not dry_run:
            try:
                brand_result = finalize_import(self.session, dry_run=False)
                self.session.commit()
                logger.info("Import committed to database")
            except Exception as e:
                self.session.rollback()
                logger.error(f"Import failed: {e}")
                raise
        else:
            logger.info("Dry run completed, no changes committed")

        # Step 4: Post-import summary
        run_post_import_summary(
            session=self.session,
            product_result=self.result,
            brand_result=brand_result,
            run_type="product_import",
            source_file=None,
            dry_run=dry_run,
            save_artifacts=True,
            validate=False,
        )

        return self.result

    def _process_identity(self, identity: ProductIdentity) -> None:
        """Process single product identity (create or update)."""

        # Build final payload
        payload = build_product_payload(identity.to_dict())

        # Try to find existing product
        existing = self._find_existing_product(identity)

        if existing:
            self._update_product(existing, payload, identity)
        else:
            self._create_product(payload, identity)

    def _find_existing_product(
        self, identity: ProductIdentity
    ) -> models.Product | None:
        """
        Find existing product by identity key.

        Priority:
        1. SKU (most reliable)
        2. Name + Brand (fallback)
        """
        # Try SKU first
        if identity.sku:
            existing = self.repo.get_by_sku(identity.sku)
            if existing:
                return existing

        # Fallback: search by name + brand
        if identity.name and identity.brand:
            candidates = self.repo.search(
                query=identity.name, brand=identity.brand, limit=5
            )

            for candidate in candidates:
                if normalize_text_for_comparison(
                    candidate.name
                ) == normalize_text_for_comparison(identity.name):
                    logger.debug(f"Found by name+brand: {identity.name}")
                    return candidate

        return None

    def _create_product(
        self, payload: dict[str, Any], identity: ProductIdentity
    ) -> None:
        """Create new product."""

        try:
            data = ProductCreate(**payload)

            if not self.result.dry_run:
                product = self.repo.create(data)
                logger.debug(f"Created product: {product.sku}")

            source_page = (payload.get("attributes_json") or {}).get("source_page")

            self.result.created += 1
            self.result.details.append(
                {
                    "page": source_page,
                    "name": identity.name,
                    "sku": identity.sku,
                    "action": "created",
                }
            )

            _ensure_result_buckets(self.result)
            if source_page is not None:
                bucket = self.result.suspicious_pages.setdefault(
                    source_page,
                    {
                        "reasons": set(),
                        "skus": set(),
                        "updated": 0,
                        "created": 0,
                        "skipped": 0,
                    },
                )
                bucket["created"] += 1

            self.result.changed_rows.append(
                {
                    "page": source_page,
                    "name": identity.name,
                    "sku": identity.sku,
                    "action": "created",
                    "old_name": None,
                    "new_name": identity.name,
                    "issue_type": None,
                    "dry_run": self.result.dry_run,
                }
            )

        except Exception as e:
            logger.error(f"Create failed for {identity.name}: {e}")
            raise

    def _update_product(
        self,
        existing: models.Product,
        payload: dict[str, Any],
        identity: ProductIdentity,
    ) -> None:
        """Update existing product with smart merge."""

        update_data: dict[str, Any] = {}
        source_page = (payload.get("attributes_json") or {}).get("source_page")
        incoming_name = payload.get("name")
        incoming_name_is_suspicious = bool(
            incoming_name and _is_suspicious_product_name(incoming_name)
        )

        # Name: update only if new name is actually better and not suspicious
        if _should_replace_product_name(existing.name, incoming_name):
            update_data["name"] = incoming_name

        if incoming_name_is_suspicious:
            logger.warning(
                "SUSPICIOUS NAME page=%s sku=%s name=%s",
                source_page,
                identity.sku,
                identity.name,
            )

        # Brand: fill if missing
        if payload.get("brand") and not existing.brand:
            update_data["brand"] = payload["brand"]

        # Category: fill if missing
        if payload.get("category") and not existing.category:
            update_data["category"] = payload["category"]

        # Description: keep longer one
        new_desc = payload.get("description")
        if new_desc:
            if not existing.description or len(new_desc) > len(existing.description):
                update_data["description"] = new_desc

        # Attributes: merge
        existing_attrs = existing.attributes_json or {}
        new_attrs = payload.get("attributes_json") or {}
        merged_attrs = existing_attrs.copy()

        if new_attrs:
            for key, value in new_attrs.items():
                if value is not None:
                    existing_val = merged_attrs.get(key)
                    if existing_val is None:
                        merged_attrs[key] = value
                    elif isinstance(existing_val, str) and isinstance(value, str):
                        if len(value) > len(existing_val):
                            merged_attrs[key] = value

            if merged_attrs != existing_attrs:
                update_data["attributes_json"] = merged_attrs

        # Source tracking
        if payload.get("source_file") and "source_file" not in existing_attrs:
            attrs = (update_data.get("attributes_json") or merged_attrs).copy()
            attrs["source_file"] = payload["source_file"]
            attrs["source_page"] = payload.get("source_page")
            update_data["attributes_json"] = attrs

        # Perform update
        if update_data:
            try:
                logger.warning(
                    "UPDATED page=%s sku=%s changes=%s old_name=%s new_name=%s dry_run=%s",
                    source_page,
                    existing.sku,
                    list(update_data.keys()),
                    existing.name,
                    incoming_name,
                    self.result.dry_run,
                )

                if not self.result.dry_run:
                    update = ProductUpdate(**update_data)
                    self.repo.update(existing, update)
                    logger.debug("Updated product: %s", existing.sku)

                issue_type = None
                if "name" in update_data:
                    issue_type = _classify_name_issue(
                        existing.name, incoming_name, identity.sku
                    )
                    if issue_type:
                        _mark_suspicious_page(
                            self.result, source_page, identity.sku, issue_type
                        )

                _ensure_result_buckets(self.result)
                if source_page is not None:
                    bucket = self.result.suspicious_pages.setdefault(
                        source_page,
                        {
                            "reasons": set(),
                            "skus": set(),
                            "updated": 0,
                            "created": 0,
                            "skipped": 0,
                        },
                    )
                    bucket["updated"] += 1

                self.result.updated += 1
                self.result.details.append(
                    {
                        "page": source_page,
                        "name": identity.name,
                        "sku": identity.sku,
                        "action": "updated",
                        "updated_fields": list(update_data.keys()),
                        "old_name": existing.name,
                        "new_name": incoming_name,
                        "issue_type": issue_type,
                        "dry_run": self.result.dry_run,
                    }
                )

                self.result.changed_rows.append(
                    {
                        "page": source_page,
                        "name": identity.name,
                        "sku": identity.sku,
                        "action": "updated",
                        "updated_fields": list(update_data.keys()),
                        "old_name": existing.name,
                        "new_name": incoming_name,
                        "issue_type": issue_type,
                        "dry_run": self.result.dry_run,
                    }
                )
                return

            except Exception as e:
                logger.error(f"Update failed for {existing.sku}: {e}")
                raise

        # Skip path
        if incoming_name_is_suspicious:
            skip_reason = "suspicious_name_blocked"
        else:
            skip_reason = "no changes needed"

        logger.warning(
            "SKIPPED page=%s sku=%s name=%s reason=%s",
            source_page,
            identity.sku,
            identity.name,
            skip_reason,
        )

        _ensure_result_buckets(self.result)
        if source_page is not None:
            bucket = self.result.suspicious_pages.setdefault(
                source_page,
                {
                    "reasons": set(),
                    "skus": set(),
                    "updated": 0,
                    "created": 0,
                    "skipped": 0,
                },
            )
            bucket["skipped"] += 1

        self.result.skipped += 1
        self.result.details.append(
            {
                "page": source_page,
                "name": identity.name,
                "sku": identity.sku,
                "action": "skipped",
                "reason": skip_reason,
            }
        )

        self.result.changed_rows.append(
            {
                "page": source_page,
                "name": identity.name,
                "sku": identity.sku,
                "action": "skipped",
                "reason": skip_reason,
                "old_name": None,
                "new_name": identity.name,
                "issue_type": (
                    "suspicious_name_blocked" if incoming_name_is_suspicious else None
                ),
                "dry_run": self.result.dry_run,
            }
        )
