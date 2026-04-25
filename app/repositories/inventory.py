from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import models
from app.schemas import InventoryUpdate


class InventoryRepository:
    def __init__(self, session: Session):
        self.session = session

    def list(self, *, offset: int = 0, limit: int = 100):
        stmt = select(models.Inventory).offset(offset).limit(limit)
        return self.session.scalars(stmt).all()

    def get_by_product_id(self, product_id: int) -> models.Inventory | None:
        stmt = select(models.Inventory).where(models.Inventory.product_id == product_id)
        return self.session.scalar(stmt)

    def upsert(self, product_id: int, update_data: InventoryUpdate) -> models.Inventory:
        inv = self.get_by_product_id(product_id)
        if not inv:
            inv = models.Inventory(product_id=product_id, stock_doc=0, stock_fact=0, reserved_qty=0)
            self.session.add(inv)
            self.session.flush()
        for key, value in update_data.model_dump(exclude_unset=True).items():
            setattr(inv, key, value)
        self.session.add(inv)
        self.session.flush()
        return inv

    def reserve(self, product_id: int, qty: float) -> models.Inventory:
        inv = self.get_by_product_id(product_id)
        if not inv:
            raise ValueError("Inventory not found for product")
        inv.reserved_qty += qty
        self.session.add(inv)
        self.session.flush()
        return inv

    def adjust_stock(self, product_id: int, stock_fact: float) -> models.Inventory:
        inv = self.get_by_product_id(product_id)
        if not inv:
            raise ValueError("Inventory not found for product")
        inv.stock_fact = stock_fact
        self.session.add(inv)
        self.session.flush()
        return inv

    def decrease_stock_doc(self, product_id: int, qty: float) -> models.Inventory:
        inv = self.get_by_product_id(product_id)
        if not inv:
            raise ValueError("Inventory not found for product")
        if inv.stock_doc < qty:
            raise ValueError("Not enough stock_doc")
        inv.stock_doc -= qty
        self.session.add(inv)
        self.session.flush()
        return inv

    def add_movement(
        self,
        *,
        product_id: int,
        movement_type: models.MovementType,
        quantity: float,
        unit: str | None,
        source: str | None,
        comment: str | None,
        created_by: int | None,
    ) -> models.StockMovement:
        movement = models.StockMovement(
            product_id=product_id,
            movement_type=movement_type,
            quantity=quantity,
            unit=unit,
            source=source,
            comment=comment,
            created_by=created_by,
        )
        self.session.add(movement)
        self.session.flush()
        return movement
