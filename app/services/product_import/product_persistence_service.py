"""Product persistence service for Excel import pipeline.

Converts built products to ProductCreate and saves via ProductRepository.
"""

import logging
from typing import Any
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.schemas.product import ProductCreate
from app.repositories.product import ProductRepository

logger = logging.getLogger(__name__)


@dataclass
class PersistenceSummary:
    """Summary of batch persistence operation."""

    total_received: int
    inserted: int
    updated: int
    failed: int
    enriched_needed: int  # Count of products needing PDF enrichment
    name_fallback_to_sku: int  # Count of products where name fell back to SKU


def _resolve_product_name(excel_title: str | None, sku: str | None) -> tuple[str, bool]:
    """Resolve product name with SKU fallback for Excel import.

    Local policy for Excel import path only:
    - If Excel title is present and non-empty -> use it
    - Otherwise -> fallback to SKU as name

    Returns:
        Tuple of (resolved_name, used_fallback)
    """
    if excel_title and str(excel_title).strip():
        return str(excel_title).strip(), False

    # Fallback to SKU - ensures product can be created even without title
    fallback = str(sku).strip() if sku else ""
    return fallback, True


def _convert_to_product_create(built_product: dict[str, Any]) -> ProductCreate:
    """Convert built product dict to ProductCreate schema - with local name fallback.

    Excel Import Path Only:
    - name = excel_title if present, else sku (fallback)
    - This keeps schema strict globally while allowing minimal-data import

    Mapping:
    - sku -> sku
    - title -> name (with SKU fallback if missing)
    - price -> price
    - currency -> currency
    - description -> description (can be None)
    - brand -> brand
    - category -> category
    - base_attributes -> attributes_json (includes needs_pdf_enrichment flag)
    """
    sku = built_product["sku"] or ""
    excel_title = built_product.get("title")

    # Local name resolution: title if present, else SKU fallback
    name, used_fallback = _resolve_product_name(excel_title, sku)

    if used_fallback:
        logger.info(
            f"[EXCEL IMPORT] Title missing for SKU={sku} -> fallback name={name}"
        )

    base_attrs = built_product.get("base_attributes") or {}

    # Track enrichment status
    needs_enrichment = base_attrs.get("needs_pdf_enrichment", False)
    if needs_enrichment:
        logger.info(f"[PERSIST] SKU={sku} flagged for PDF enrichment")

    return ProductCreate(
        sku=sku,
        name=name,  # Always has value: title or SKU fallback
        brand=built_product.get("brand"),
        category=built_product.get("category"),
        unit=None,
        price=built_product.get("price"),
        currency=built_product.get("currency"),
        description=built_product.get("description"),  # Can be None
        attributes_json=base_attrs,
        is_active=True,
    )


def persist_products(
    session: Session,
    built_products: list[dict[str, Any]],
) -> PersistenceSummary:
    """Persist built products to database using upsert - SKU-FIRST approach.

    Args:
        session: Database session
        built_products: List of built product dictionaries

    Returns:
        PersistenceSummary with counts
    """
    repo = ProductRepository(session)

    inserted = 0
    updated = 0
    failed = 0
    enriched_needed = 0
    name_fallback_count = 0

    for product_dict in built_products:
        try:
            # Skip engineering SKUs marked for skip
            base_attrs = product_dict.get("base_attributes") or {}
            if base_attrs.get("_skipped_reason") == "engineering_sku_out_of_scope":
                logger.info(
                    f"[PERSIST] SKIPPED engineering SKU: {product_dict.get('sku')}"
                )
                continue

            product_create = _convert_to_product_create(product_dict)

            # Track enrichment needs
            attrs = product_create.attributes_json or {}
            if attrs.get("needs_pdf_enrichment", False):
                enriched_needed += 1

            # Track name fallback
            if (
                product_dict.get("title") is None
                or str(product_dict.get("title", "")).strip() == ""
            ):
                name_fallback_count += 1

            sku = product_create.sku
            _, was_created = repo.upsert_by_sku(product_create)

            if was_created:
                inserted += 1
                logger.info(
                    f"[PERSIST] CREATED product SKU={sku}, name={product_create.name}"
                )
            else:
                updated += 1
                logger.info(
                    f"[PERSIST] UPDATED product SKU={sku}, name={product_create.name}"
                )

        except Exception as e:
            failed += 1
            sku = product_dict.get("sku", "UNKNOWN")
            logger.error(f"[PERSIST] FAILED for SKU={sku}: {e}")
            # Continue with next product

    logger.info(
        f"[PERSIST SUMMARY] total={len(built_products)}, inserted={inserted}, "
        f"updated={updated}, failed={failed}, needs_enrichment={enriched_needed}, "
        f"name_fallback_to_sku={name_fallback_count}"
    )

    return PersistenceSummary(
        total_received=len(built_products),
        inserted=inserted,
        updated=updated,
        failed=failed,
        enriched_needed=enriched_needed,
        name_fallback_to_sku=name_fallback_count,
    )
