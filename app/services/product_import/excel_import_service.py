from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy.orm import Session

from app.services.product_import.excel_loader import ExcelLoader
from app.services.product_import.excel_mapper import (
    map_column_aliases,
    map_raw_row_to_excel_schema,
)
from app.services.product_import.excel_normalizer import normalize_excel_row
from app.services.product_import.merge_service import MergeService, _is_weak_title
from app.services.product_import.product_persistence_service import (
    PersistenceSummary,
    persist_products,
)

logger = logging.getLogger(__name__)


@dataclass
class ExcelCatalogImportResult:
    filename: str
    sheet: str
    header_row: int
    raw_rows: int
    mapped_rows: int
    built_products: int
    inserted: int
    updated: int
    failed: int
    needs_pdf_enrichment: int
    name_fallback_to_sku: int
    title_empty_in_excel: int
    weak_title_after_normalize: int
    title_lost_in_mapper: int
    title_column_not_mapped: int


def import_excel_catalog_file(
    session: Session,
    file_path: str | Path,
    *,
    filename: str,
    sheet_name: str | None = None,
    header_row: int = 2,
) -> ExcelCatalogImportResult:
    """Import product catalog Excel into the database.

    This is the API-safe version of scripts/import_excel_products.py.
    It intentionally uses the same Excel-first pipeline and persists by SKU.
    """
    loader = ExcelLoader(file_path)
    sheet_names = loader.read_sheet_names()
    selected_sheet = sheet_name or (sheet_names[0] if sheet_names else None)
    if not selected_sheet:
        raise ValueError("Excel workbook has no sheets")

    raw_rows = loader.load_excel_rows(
        sheet_name=selected_sheet,
        header_row=header_row,
    )
    headers = list(raw_rows[0].keys()) if raw_rows else []
    column_mapping = map_column_aliases(headers)

    logger.info(
        "Catalog Excel import mapping: filename=%s sheet=%s header_row=%s mapping=%s",
        filename,
        selected_sheet,
        header_row,
        column_mapping,
    )

    mapped_rows: list[tuple[int, dict, dict]] = []
    for idx, raw_row in enumerate(raw_rows):
        mapped = map_raw_row_to_excel_schema(
            raw_row=raw_row,
            column_mapping=column_mapping,
            source_file=filename,
            source_sheet=selected_sheet,
            source_row_index=idx,
        )
        if mapped is not None:
            mapped_rows.append((idx, raw_row, mapped))

    merge_service = MergeService()
    products: list[dict] = []
    title_empty_in_excel = 0
    weak_title_after_normalize = 0
    title_lost_in_mapper = 0
    title_column_not_mapped = 0
    title_excel_header = column_mapping.get("title")

    for _, raw_row, mapped_row in mapped_rows:
        normalized_row = normalize_excel_row(mapped_row)
        product = merge_service.build_product_from_excel(normalized_row)
        products.append(product)

        base_attrs = product.get("base_attributes") or {}
        needs_enrichment = bool(base_attrs.get("needs_pdf_enrichment", False))
        unified_title = product.get("title")
        mapped_title = mapped_row.get("title") if mapped_row else None

        if needs_enrichment or _is_weak_title(unified_title):
            raw_title_value = raw_row.get(title_excel_header) if title_excel_header else None
            raw_title = str(raw_title_value).strip() if raw_title_value is not None else ""

            if title_excel_header is None:
                title_column_not_mapped += 1
            elif raw_title == "":
                title_empty_in_excel += 1
            elif mapped_title is None or str(mapped_title).strip() == "":
                title_lost_in_mapper += 1
            elif _is_weak_title(unified_title):
                weak_title_after_normalize += 1

    summary: PersistenceSummary = persist_products(session, products)

    return ExcelCatalogImportResult(
        filename=filename,
        sheet=selected_sheet,
        header_row=header_row,
        raw_rows=len(raw_rows),
        mapped_rows=len(mapped_rows),
        built_products=len(products),
        inserted=summary.inserted,
        updated=summary.updated,
        failed=summary.failed,
        needs_pdf_enrichment=summary.enriched_needed,
        name_fallback_to_sku=summary.name_fallback_to_sku,
        title_empty_in_excel=title_empty_in_excel,
        weak_title_after_normalize=weak_title_after_normalize,
        title_lost_in_mapper=title_lost_in_mapper,
        title_column_not_mapped=title_column_not_mapped,
    )

