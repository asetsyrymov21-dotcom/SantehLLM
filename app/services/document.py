from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional, Tuple

from openpyxl import load_workbook
from sqlalchemy.orm import Session

from app.db import models
from app.repositories.document import DocumentRepository
from app.repositories.sale import SaleRepository
from app.schemas import DocumentRead

logger = logging.getLogger(__name__)
TEMPLATE_PATH = Path("app/documents/templates/invoice_template.xlsx")
OUTPUT_DIR = Path("storage/generated_documents")


class DocumentService:
    def __init__(self, session: Session):
        self.session = session
        self.docs = DocumentRepository(session)
        self.sales = SaleRepository(session)

    def create_invoice_for_sale(self, sale_id: int) -> Optional[DocumentRead]:
        sale = self.sales.get(sale_id)
        if not sale:
            return None
        if not TEMPLATE_PATH.exists():
            raise FileNotFoundError("Invoice template not found")

        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        outfile = OUTPUT_DIR / f"invoice_{sale.sale_number}.xlsx"

        wb = load_workbook(TEMPLATE_PATH)
        ws = wb.active

        ws["B2"] = sale.sale_number
        ws["B3"] = sale.sale_date.strftime("%Y-%m-%d")

        start_row = 6
        for idx, item in enumerate(sale.items, start=1):
            row = start_row + idx - 1
            ws[f"A{row}"] = idx
            ws[f"B{row}"] = item.product_name_snapshot
            ws[f"C{row}"] = item.sku_snapshot or ""
            ws[f"D{row}"] = float(item.quantity)
            ws[f"E{row}"] = float(item.unit_price)
            ws[f"F{row}"] = float(item.line_total)

        total_row = start_row + len(sale.items) + 1
        ws[f"E{total_row}"] = "Итого:"
        ws[f"F{total_row}"] = float(sale.total_amount)

        wb.save(outfile)

        doc = self.docs.create(
            document_type="invoice",
            document_number=sale.sale_number,
            status=models.DocumentStatus.READY,
            related_sale_id=sale.id,
            file_path=str(outfile),
        )
        self.session.commit()
        return DocumentRead.model_validate(doc, from_attributes=True)

    def get_document_file(self, document_id: int) -> Tuple[str, str]:
        doc = self.docs.get(document_id)
        if not doc:
            raise FileNotFoundError("Document not found")
        if not doc.file_path:
            raise FileNotFoundError("Document file is missing")
        path = Path(doc.file_path)
        if not path.exists():
            raise FileNotFoundError("Document file is missing")
        return str(path), path.name
