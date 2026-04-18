from __future__ import annotations

import logging
import tempfile
import os

from fastapi import APIRouter, Depends, File, UploadFile, HTTPException
from sqlalchemy.orm import Session

from app.api import deps
from app.schemas import ImportCatalogResponse, StockImportResponse
from app.services.import_service import ImportService
from app.services.stock_import.excel_parser import StockExcelParser
from app.services.stock_import.matcher import StockMatcher
from app.services.stock_import.importer import StockImporter

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/imports", tags=["imports"])


@router.post("/catalog", response_model=ImportCatalogResponse)
def import_catalog(
    file: UploadFile = File(...),
    service: ImportService = Depends(deps.get_import_service),
) -> ImportCatalogResponse:
    if not file.filename:
        raise HTTPException(status_code=400, detail="File is required")
    return service.import_catalog(file)


@router.post("/inventory", response_model=StockImportResponse)
def import_inventory(
    file: UploadFile = File(...),
    session: Session = Depends(deps.get_session),
) -> StockImportResponse:
    if not file.filename:
        raise HTTPException(status_code=400, detail="File is required")

    if not file.filename.lower().endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="Only .xlsx files are supported")

    # Save uploaded file to a temp file (StockExcelParser needs a path)
    content = file.file.read()
    with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    try:
        # Step 1: parse Excel
        parser = StockExcelParser(tmp_path)
        try:
            parse_result = parser.parse(use_default_sheets=True)
        except ValueError:
            logger.warning(
                "Inventory parse failed on default sheets: file=%s filename=%s",
                tmp_path,
                file.filename,
                exc_info=True,
            )
            try:
                parse_result = parser.parse(sheet_name=1, use_default_sheets=False)
            except ValueError:
                logger.error(
                    "Inventory parse failed on second sheet fallback: file=%s filename=%s",
                    tmp_path,
                    file.filename,
                    exc_info=True,
                )
                raise

        # Step 2: match SKUs against DB
        matcher = StockMatcher(session, brand_filter=None)
        report = matcher.match_rows(parse_result.rows)

        # Step 3: commit updates
        importer = StockImporter(session, source_file=file.filename)
        result = importer.commit(report, skip_duplicates=True)

        # Step 4: generate and log summary
        summary = result.generate_summary(source_file=file.filename)
        summary.log_summary(logger)

        # CRITICAL: Fail if any products have NULL brand
        if summary.total_brand_null != 0:
            session.rollback()
            raise HTTPException(
                status_code=500,
                detail=f"Import failed: total_brand_null={summary.total_brand_null}. All products must have a brand.",
            )

        session.commit()

    except Exception as e:
        session.rollback()
        logger.exception(
            "Inventory import failed: file=%s filename=%s",
            tmp_path,
            file.filename,
        )
        raise HTTPException(status_code=500, detail=f"Import failed: {str(e)}")
    finally:
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
