from __future__ import annotations

import json
import logging
from typing import List

from fastapi import UploadFile
from sqlalchemy.orm import Session

from app.repositories.product import ProductRepository
from app.schemas import ImportCatalogResponse, ImportCatalogError, ProductCreate
from app.utils.excel import read_catalog_bytes
from app.utils.pdf_parser import extract_tables_from_pdf

import re

logger = logging.getLogger(__name__)


def _is_suspicious_name(name: str) -> bool:
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


class ImportService:
    def __init__(self, session: Session):
        self.session = session
        self.products = ProductRepository(session)

    def import_catalog(self, file: UploadFile) -> ImportCatalogResponse:
        content = file.file.read()
        filename = file.filename or ""

        if filename.lower().endswith(".pdf"):
            rows = extract_tables_from_pdf(content)
        elif filename.lower().endswith((".xlsx", ".xls")):
            rows = read_catalog_bytes(content)
        else:
            try:
                rows = read_catalog_bytes(content)
            except Exception:
                rows = extract_tables_from_pdf(content)

        return self._process_catalog_rows(rows)

    def _process_catalog_rows(self, rows: List[dict]) -> ImportCatalogResponse:
        created = updated = skipped = 0
        errors: List[ImportCatalogError] = []

        for idx, row in enumerate(rows, start=2):
            try:
                payload = self._row_to_product(row)
                product, is_created = self.products.upsert_by_sku(payload)
                if is_created:
                    created += 1
                else:
                    updated += 1
            except Exception as exc:
                logger.exception("Catalog import row failed", extra={"row": idx})
                errors.append(ImportCatalogError(row=idx, error=str(exc)))
                skipped += 1
        self.session.commit()

        return ImportCatalogResponse(
            total_rows=len(rows),
            created=created,
            updated=updated,
            skipped=skipped,
            errors=errors,
        )

    def _row_to_product(self, row: dict) -> ProductCreate:
        attributes = row.get("attributes_json")
        if isinstance(attributes, str):
            try:
                attributes = json.loads(attributes)
            except json.JSONDecodeError:
                attributes = None
        elif isinstance(attributes, dict):
            pass
        else:
            attributes = None

        sku = str(row["sku"]).strip()
        name = str(row["name"]).strip()

        if _is_suspicious_name(name):
            raise ValueError(f"suspicious product name for sku={sku}: {name[:120]}")

        return ProductCreate(
            sku=sku,
            name=name,
            brand=row.get("brand"),
            category=row.get("category"),
            unit=row.get("unit"),
            price=float(row["price"]) if row.get("price") is not None else None,
            currency=row.get("currency"),
            description=row.get("description"),
            attributes_json=attributes,
            is_active=bool(row.get("is_active", True)),
        )
