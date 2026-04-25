from __future__ import annotations

from typing import Sequence

from sqlalchemy.orm import Session

from app.repositories.inventory import InventoryRepository
from app.schemas import InventoryRead, InventoryUpdate


class InventoryService:
    def __init__(self, session: Session):
        self.session = session
        self.repo = InventoryRepository(session)

    def list(self, offset: int = 0, limit: int = 100) -> list[InventoryRead]:
        invs: Sequence = self.repo.list(offset=offset, limit=limit)
        return [InventoryRead.model_validate(inv) for inv in invs]

    def get(self, product_id: int) -> InventoryRead | None:
        inv = self.repo.get_by_product_id(product_id)
        if inv:
            return InventoryRead.model_validate(inv)
        return None

    def update(self, product_id: int, payload: InventoryUpdate) -> InventoryRead | None:
        inv = self.repo.upsert(product_id, payload)
        self.session.commit()
        return InventoryRead.model_validate(inv)
