from __future__ import annotations

from typing import Sequence

from sqlalchemy.orm import Session

from app.db import models
from app.repositories.inventory import InventoryRepository
from app.repositories.sale import SaleRepository
from app.schemas import SaleCreate, SaleRead


class SalesService:
    def __init__(self, session: Session):
        self.session = session
        self.repo = SaleRepository(session)
        self.inventory_repo = InventoryRepository(session)

    def create(self, payload: SaleCreate) -> SaleRead:
        total = sum((item.line_total for item in payload.items), 0)
        sale = self.repo.create(payload, total_amount=total)
        self.session.commit()
        return SaleRead.model_validate(sale, from_attributes=True)

    def confirm(self, sale_id: int) -> SaleRead:
        sale = self.repo.get(sale_id)
        if not sale:
            raise ValueError("Sale not found")
        if sale.status == models.SaleStatus.CONFIRMED:
            return SaleRead.model_validate(sale, from_attributes=True)

        # validate stock for all items first
        for item in sale.items:
            inv = self.inventory_repo.get_by_product_id(item.product_id) if item.product_id else None
            if inv is None or inv.stock_doc < item.quantity:
                raise ValueError(f"Недостаточно остатка для товара {item.sku_snapshot or item.product_name_snapshot}")

        # apply decrements and movements
        for item in sale.items:
            if item.product_id:
                self.inventory_repo.decrease_stock_doc(item.product_id, item.quantity)
                self.inventory_repo.add_movement(
                    product_id=item.product_id,
                    movement_type=models.MovementType.OUTBOUND,
                    quantity=item.quantity,
                    unit=item.unit,
                    source="sale",
                    comment=f"Sale {sale.sale_number}",
                    created_by=sale.created_by,
                )

        self.repo.update_status(sale, models.SaleStatus.CONFIRMED)
        self.session.commit()
        return SaleRead.model_validate(sale, from_attributes=True)

    def cancel(self, sale_id: int) -> SaleRead:
        sale = self.repo.get(sale_id)
        if not sale:
            raise ValueError("Sale not found")
        if sale.status == models.SaleStatus.CANCELLED:
            return SaleRead.model_validate(sale, from_attributes=True)
        if sale.status != models.SaleStatus.CONFIRMED:
            raise ValueError("Можно отменить только подтвержденную продажу")

        # ensure inventory exists
        for item in sale.items:
            if not item.product_id:
                continue
            inv = self.inventory_repo.get_by_product_id(item.product_id)
            if inv is None:
                raise ValueError(f"Не найден inventory для товара {item.sku_snapshot or item.product_name_snapshot}")

        # rollback stock_doc and add inbound movements
        for item in sale.items:
            if not item.product_id:
                continue
            inv = self.inventory_repo.get_by_product_id(item.product_id)
            inv.stock_doc += item.quantity
            self.inventory_repo.add_movement(
                product_id=item.product_id,
                movement_type=models.MovementType.INBOUND,
                quantity=item.quantity,
                unit=item.unit,
                source="sale_cancel",
                comment=f"Cancel sale {sale.sale_number}",
                created_by=sale.created_by,
            )

        self.repo.update_status(sale, models.SaleStatus.CANCELLED)
        self.session.commit()
        return SaleRead.model_validate(sale, from_attributes=True)

    def get(self, sale_id: int) -> SaleRead | None:
        sale = self.repo.get(sale_id)
        if sale:
            return SaleRead.model_validate(sale, from_attributes=True)
        return None

    def list(self, offset: int = 0, limit: int = 100) -> Sequence[SaleRead]:
        sales = self.repo.list(offset=offset, limit=limit)
        return [SaleRead.model_validate(s, from_attributes=True) for s in sales]
