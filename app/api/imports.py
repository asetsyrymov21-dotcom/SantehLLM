from __future__ import annotations

import logging
import tempfile
import os

from fastapi import APIRouter, Depends, File, UploadFile, HTTPException
from sqlalchemy.orm import Session

from app.api import deps
from app.schemas import (
    CatalogExcelImportResponse,
    ImportCatalogResponse,
    StockImportResponse,
)
from app.services.import_service import ImportService
from app.services.product_import.excel_import_service import import_excel_catalog_file
from app.services.stock_import.excel_parser import StockExcelParser
from app.services.stock_import.text_parser import parse_stock_text_file
from app.services.stock_import.matcher import StockMatcher
from app.services.stock_import.importer import StockImporter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/imports", tags=["imports"])

MAX_EXCEL_UPLOAD_BYTES = 120 * 1024 * 1024
STOCK_HEADER_ROWS_TO_TRY = range(0, 10)


class StockQuantityColumnMissingError(ValueError):
    """Raised when an Excel file has SKU/article headers but no stock column."""


def _parse_stock_excel_file(path: str) -> object:
    last_error: Exception | None = None
    article_only_result: object | None = None

    for header_row in STOCK_HEADER_ROWS_TO_TRY:
        parser = StockExcelParser(path, header_row=header_row)
        try:
            parse_result = parser.parse(use_default_sheets=True)
        except ValueError as e:
            last_error = e
            logger.info(
                "Inventory parse failed with header_row=%s: %s",
                header_row,
                e,
            )
            continue

        if "quantity" not in parse_result.column_mapping:
            article_only_result = article_only_result or parse_result
            logger.info(
                "Inventory parse found article but no quantity: header_row=%s",
                header_row,
            )
            continue

        logger.info("Inventory headers detected with header_row=%s", header_row)
        return parse_result

    if article_only_result is not None:
        header_columns = (
            list(article_only_result.rows[0].raw_data.keys())
            if article_only_result.rows
            else list(article_only_result.column_mapping.values())
        )
        columns = ", ".join(
            f"'{column}'"
            for column in header_columns[:20]
            if column and not str(column).startswith("Unnamed:")
        )
        raise StockQuantityColumnMissingError(
            "Это похоже на прайс-лист без колонки остатков: найдена колонка "
            "артикула, но не найдена колонка количества/остатка. "
            "Склад не изменён. Загрузите файл остатков с колонкой "
            "'Остаток', 'Количество', 'Qty', 'Stock' или 'Шт'. "
            f"Колонки файла: {columns or 'нет'}."
        )

    raise ValueError(
        "Не удалось найти колонки остатков в Excel. "
        "Файл должен содержать колонку артикула и колонку количества/остатка. "
        f"Last parser error: {last_error}"
    )


@router.post("/catalog", response_model=ImportCatalogResponse)
def import_catalog(
    file: UploadFile = File(...),
    service: ImportService = Depends(deps.get_import_service),
) -> ImportCatalogResponse:
    if not file.filename:
        raise HTTPException(status_code=400, detail="File is required")
    return service.import_catalog(file)


@router.post("/catalog-excel", response_model=CatalogExcelImportResponse)
def import_catalog_excel(
    file: UploadFile = File(...),
    header_row: int = 2,
    session: Session = Depends(deps.get_session),
) -> CatalogExcelImportResponse:
    if not file.filename:
        raise HTTPException(status_code=400, detail="File is required")

    if not file.filename.lower().endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="Only .xlsx files are supported")

    content = file.file.read()
    if len(content) > MAX_EXCEL_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Excel file is too large")

    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    try:
        result = import_excel_catalog_file(
            session,
            tmp_path,
            filename=file.filename,
            header_row=header_row,
        )
        session.commit()
    except Exception as e:
        session.rollback()
        logger.exception(
            "Catalog Excel import failed: file=%s filename=%s",
            tmp_path,
            file.filename,
        )
        raise HTTPException(status_code=500, detail=f"Import failed: {str(e)}")
    finally:
        os.unlink(tmp_path)

    return CatalogExcelImportResponse(**result.__dict__)


@router.post("/inventory", response_model=StockImportResponse)
def import_inventory(
    file: UploadFile = File(...),
    session: Session = Depends(deps.get_session),
) -> StockImportResponse:
    if not file.filename:
        raise HTTPException(status_code=400, detail="File is required")

    filename = file.filename
    filename_lower = filename.lower()
    if not filename_lower.endswith((".xlsx", ".csv", ".txt")):
        raise HTTPException(
            status_code=400,
            detail="Only .xlsx, .csv and .txt files are supported",
        )

    content = file.file.read()
    tmp_path = None

    try:
        # Step 1: parse source file
        if filename_lower.endswith(".xlsx"):
            # Save uploaded file to a temp file (StockExcelParser needs a path)
            with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
                tmp.write(content)
                tmp_path = tmp.name

            parse_result = _parse_stock_excel_file(tmp_path)
        else:
            parse_result = parse_stock_text_file(content, filename)

        # Step 2: match SKUs against DB
        matcher = StockMatcher(session, brand_filter=None)
        report = matcher.match_rows(parse_result.rows)

        # Step 3: commit updates
        importer = StockImporter(session, source_file=filename)
        result = importer.commit(report, skip_duplicates=True)

        # Step 4: generate and log summary
        summary = result.generate_summary(source_file=filename)
        summary.log_summary(logger)

        # CRITICAL: Fail if any products have NULL brand
        if summary.total_brand_null != 0:
            session.rollback()
            raise HTTPException(
                status_code=500,
                detail=f"Import failed: total_brand_null={summary.total_brand_null}. All products must have a brand.",
            )

        session.commit()

    except HTTPException:
        session.rollback()
        raise
    except ValueError as e:
        session.rollback()
        logger.warning(
            "Inventory import validation failed: file=%s filename=%s error=%s",
            tmp_path,
            filename,
            e,
        )
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        session.rollback()
        logger.exception(
            "Inventory import failed: file=%s filename=%s",
            tmp_path,
            filename,
        )
        raise HTTPException(status_code=500, detail=f"Import failed: {str(e)}")
    finally:
        if tmp_path:
            os.unlink(tmp_path)

    return StockImportResponse(
        rows_scanned=result.rows_scanned_from_source,
        updated=result.updated,
        unchanged=result.unchanged,
        skipped_no_product=result.skipped_no_product,
        skipped_unsupported_brand=result.skipped_unsupported_brand,
        skipped_invalid_sku=result.skipped_invalid_sku,
        skipped_invalid_qty=result.skipped_invalid_qty,
        skipped_duplicate=result.skipped_duplicate,
        empty_qty_treated_as_zero=result.empty_qty_treated_as_zero,
        errors=result.errors,
    )
