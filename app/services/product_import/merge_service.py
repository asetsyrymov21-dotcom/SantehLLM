"""Merge service for combining Excel and PDF product data.

Coordinates the unification of data from multiple sources.
"""

import re
import logging
from typing import Any
from dataclasses import dataclass

logger = logging.getLogger(__name__)


def extract_category_from_name(name: str | None) -> str | None:
    """Extract category from product name."""
    if not name:
        return None
    name_lower = name.lower()
    if "смес." in name_lower or "смеситель" in name_lower:
        return "смеситель"
    return None


def extract_attributes_from_name(name: str | None) -> dict[str, Any]:
    """Extract structured attributes from product name."""
    if not name:
        return {}

    attributes: dict[str, Any] = {}
    name_lower = name.lower()

    # finish
    if "хром" in name_lower:
        attributes["finish"] = "хром"

    # application
    if "д/раковины" in name_lower:
        attributes["application"] = "раковина"
    elif "д/душа" in name_lower:
        attributes["application"] = "душ"
    elif "д/ван." in name_lower or "д/ванны" in name_lower:
        attributes["application"] = "ванна"

    # diameter: ф40, Ф40
    match = re.search(r"(?:ф|Ф)\s*(\d+)", name)
    if match:
        try:
            attributes["diameter_mm"] = int(match.group(1))
        except ValueError:
            pass

    # spout: излив 30S
    match = re.search(r"излив\s+(\d+[Ss]?\d*)", name, re.IGNORECASE)
    if match:
        attributes["spout"] = match.group(1).upper()

    # switch type
    if "дивертор" in name_lower:
        attributes["switch_type"] = "дивертор"

    # cartridge
    if "картридж" in name_lower:
        attributes["cartridge"] = True

    return attributes


def _is_engineering_sku(sku: str | None) -> bool:
    """Check if SKU is from engineering catalog (out of scope for this patch).

    Engineering SKUs like F101.2004 are from a different catalog.
    """
    if not sku:
        return False
    # Engineering SKUs contain dots and follow different patterns
    # e.g., F101.2004, F201.1503
    return bool(re.search(r"^[A-Z]\d{3}\.\d{4}$", str(sku).strip(), re.IGNORECASE))


def _is_weak_title(title: str | None) -> bool:
    """Check if product title is weak/insufficient.

    Weak titles:
    - Empty or None
    - Just SKU repeated
    - Too short (< 5 chars)
    - Just category marker without description
    """
    if not title:
        return True

    title = str(title).strip()
    if len(title) < 5:
        return True

    # If title is just like "F1002-B" (just SKU-like)
    if re.match(r"^[A-Z]\d{3,4}[-A-Z0-9]*$", title, re.IGNORECASE) and len(title) < 15:
        return True

    return False


def _is_weak_description(description: str | None) -> bool:
    """Check if product description is weak/insufficient."""
    if not description:
        return True

    desc = str(description).strip()
    # Less than 10 chars is definitely weak
    if len(desc) < 10:
        return True

    return False


class MergeService:
    """Service for merging product data from multiple sources."""

    def __init__(self):
        # TODO: Add configuration for merge strategies
        pass

    def build_product_from_excel(self, excel_row: dict[str, Any]) -> dict[str, Any]:
        """Create unified product from Excel row only - SKU-FIRST approach.

        Rules:
        1. Product identity is based ONLY on SKU
        2. Import even if only SKU + price present
        3. Missing description does NOT cause skip
        4. If title/description missing or weak -> needs_pdf_enrichment = true
        5. Save short name/title from Excel if present
        6. Engineering SKUs (F101.2004) are out of scope

        Args:
            excel_row: Normalized Excel row data

        Returns:
            ProductUnified-like dictionary
        """
        sku = excel_row.get("sku")
        title = excel_row.get("title")
        price = excel_row.get("price")

        # Log the import attempt
        logger.info(
            f"[EXCEL IMPORT] Processing SKU={sku}, title_present={title is not None}, price_present={price is not None}"
        )

        # Skip engineering SKUs - out of scope for this patch
        if _is_engineering_sku(sku):
            logger.info(f"[EXCEL IMPORT] SKIPPED engineering SKU (out of scope): {sku}")
            return {
                "product_id": sku,
                "sku": sku,
                "title": title,
                "brand": None,
                "category": None,
                "description": None,
                "base_attributes": {"_skipped_reason": "engineering_sku_out_of_scope"},
                "extended_attributes": {},
                "price": price,
                "discount_price": excel_row.get("discount_price"),
                "stock_qty": excel_row.get("stock_qty"),
                "stock_status": "unknown",
                "currency": excel_row.get("currency", "KZT"),
                "pdf_pages": [],
                "images": [],
                "source_refs": [
                    {
                        "source": "excel",
                        "file": excel_row.get("source_file", ""),
                        "sheet": excel_row.get("source_sheet", ""),
                        "row_index": excel_row.get("source_row_index", 0),
                    }
                ],
                "merge_status": "skipped_engineering_sku",
                "confidence": 0.0,
                "field_provenance": {},
                "merge_decisions": [],
            }

        # Extract from name
        category = extract_category_from_name(title)
        name_attrs = extract_attributes_from_name(title)

        # Merge attributes: name-derived first, then Excel base_attributes override
        base_attrs = excel_row.get("base_attributes") or {}
        merged_attrs = {**name_attrs, **base_attrs}

        # Determine if PDF enrichment is needed
        # needs_pdf_enrichment = true ONLY when title is weak/missing (NOT just because description is missing)
        needs_pdf_enrichment = _is_weak_title(title)

        if needs_pdf_enrichment:
            logger.info(
                f"[EXCEL IMPORT] needs_pdf_enrichment=true for SKU={sku}: weak or missing title"
            )
        else:
            logger.info(
                f"[EXCEL IMPORT] Successfully imported from excel: SKU={sku} with good title"
            )

        # Store enrichment flag in attributes (avoiding DB migration)
        merged_attrs["needs_pdf_enrichment"] = needs_pdf_enrichment

        # Track missing description separately - this does NOT trigger enrichment
        if not excel_row.get("description"):
            merged_attrs["description_missing_in_excel"] = True
            logger.info(
                f"[EXCEL IMPORT] description_missing_in_excel=true for SKU={sku}"
            )

        return {
            "product_id": sku,
            "sku": sku,
            "title": title if title else None,  # Save short name if present, else null
            "brand": None,
            "category": category,
            "description": excel_row.get(
                "description"
            ),  # Can be None - will be enriched later
            "base_attributes": merged_attrs,
            "extended_attributes": {},
            "price": price,
            "discount_price": excel_row.get("discount_price"),
            "stock_qty": excel_row.get("stock_qty"),
            "stock_status": "unknown",
            "currency": excel_row.get("currency", "KZT"),
            "pdf_pages": [],
            "images": [],
            "source_refs": [
                {
                    "source": "excel",
                    "file": excel_row.get("source_file", ""),
                    "sheet": excel_row.get("source_sheet", ""),
                    "row_index": excel_row.get("source_row_index", 0),
                }
            ],
            "merge_status": "excel_only",
            "confidence": 1.0,
            "field_provenance": {},
            "merge_decisions": [],
        }

    def merge_excel_and_pdf(
        self,
        excel_row: Any,
        pdf_data: Any,
    ) -> Any:
        """Merge Excel row with PDF extraction results.

        Args:
            excel_row: Normalized Excel row
            pdf_data: Extracted PDF product data

        Returns:
            Merged ProductUnified instance
        """
        # TODO: Implement priority-based field merging
        # TODO: Call attach_field_provenance for each field
        raise NotImplementedError("Excel+PDF merge not implemented")

    def attach_field_provenance(
        self,
        product: Any,
        field_name: str,
        value: Any,
        source: str,
        confidence: float,
    ) -> None:
        """Attach provenance metadata to a field.

        Args:
            product: Product instance to modify
            field_name: Name of the field
            value: Final resolved value
            source: Source type (excel/pdf/llm/manual)
            confidence: Confidence score 0-1
        """
        # TODO: Implement provenance tracking
        pass

    def resolve_conflicts(
        self,
        field_name: str,
        candidates: list[tuple[Any, str, float]],
    ) -> tuple[Any, str, float]:
        """Resolve conflicting values from multiple sources.

        Args:
            field_name: Name of the field with conflict
            candidates: List of (value, source, confidence) tuples

        Returns:
            Selected (value, source, confidence)
        """
        # TODO: Implement conflict resolution strategy
        # TODO: Use merge_rules for priority lookup
        raise NotImplementedError("Conflict resolution not implemented")
