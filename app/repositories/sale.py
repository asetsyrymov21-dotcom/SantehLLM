from __future__ import annotations

from typing import Sequence

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import models
from app.schemas import SaleCreate, SaleItemCreate


class SaleRepository:
    def __init__(self, session: Session):
        self.session = session

    def get(self, sale_id: int) -> models.Sale | None:
        return self.session.get(models.Sale, sale_id)

    def get_by_number(self, sale_number: str) -> models.Sale | None:
        stmt = select(models.Sale).where(models.Sale.sale_number == sale_number)
        return self.session.scalar(stmt)

    def list(self, *, offset: int = 0, limit: int = 100) -> Sequence[models.Sale]:
        stmt = select(models.Sale).offset(offset).limit(limit)
        return self.session.scalars(stmt).all()

    def create(self, data: SaleCreate, total_amount: float) -> models.Sale:
        sale = models.Sale(
            sale_number=data.sale_number,
            sale_date=data.sale_date,
            source_type=data.source_type,
            status=data.status,
            customer_name=data.customer_name,
            total_amount=total_amount,
            currency=data.currency,
            raw_input_text=data.raw_input_text,
            created_by=data.created_by,
        )
        self.session.add(sale)
        self.session.flush()
        self._add_items(sale, data.items)
        self.session.flush()
        return sale

    def _add_items(self, sale: models.Sale, items: list[SaleItemCreate]) -> None:
        for item in items:
            sale_item = models.SaleItem(
                sale_id=sale.id,
                product_id=item.product_id,
                product_name_snapshot=item.product_name_snapshot,
                sku_snapshot=item.sku_snapshot,
                quantity=item.quantity,
                unit=item.unit,
                unit_price=item.unit_price,
                line_total=item.line_total,
            )
            self.session.add(sale_item)

    def update_status(self, sale: models.Sale, status: models.SaleStatus) -> models.Sale:
        sale.status = status
        self.session.add(sale)
        self.session.flush()
        return sale

    def add_document(self, sale: models.Sale, document: models.Document) -> None:
        sale.documents.append(document)
        self.session.add(sale)
        self.session.flush()
