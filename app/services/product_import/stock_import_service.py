"""Minimal stock import service. Matches by SKU, upserts inventory.

Duplicate SKU rule: last row wins (rows processed in file order).
"""

from dataclasses import dataclass
from typing import Any

from sqlalchemy.orm import Session

from app.repositories.product import ProductRepository
from app.repositories.inventory import InventoryRepository
from app.schemas import InventoryUpdate


@dataclass
class StockImportResult:
    total_received: int = 0
    matched: int = 0
    upserted: int = 0
    unmatched: int = 0
    skipped: int = 0
    failed: int = 0


def _get_row_value_case_insensitive(
    row: dict[str, Any], candidates: list[str]
) -> Any | None:
    lowered = {str(k).strip().lower(): v for k, v in row.items()}
    for key in candidates:
        if key.lower() in lowered:
            return lowered[key.lower()]
    return None


class StockImportService:
    def __init__(self, session: Session):
        self.session = session
        self.product_repo = ProductRepository(session)
        self.inventory_repo = InventoryRepository(session)

    def import_stock_rows(self, rows: list[dict[str, Any]]) -> StockImportResult:
        """Import stock rows. Duplicate SKUs: last row wins (processed in order).

        Args:
            rows: List of row dicts from Excel loader.

        Returns:
            StockImportResult with counts.
        """
        result = StockImportResult(total_received=len(rows))

        # Track processed SKUs for duplicate handling (last row wins)
        processed_skus: set[str] = set()

        for row in rows:
            try:
                outcome = self._process_single_row(row, processed_skus)
                if outcome == "upserted":
                    result.upserted += 1
                    result.matched += 1
                elif outcome == "unmatched":
                    result.unmatched += 1
                elif outcome == "skipped":
                    result.skipped += 1
            except Exception as e:
                print(f"ROW FAILED: row={row} error={e}")
                result.failed += 1

        return result

    def _process_single_row(self, row: dict[str, Any], processed_skus: set[str]) -> str:
        """Process single row. Returns: upserted/unmatched/skipped."""
        sku = self._extract_sku(row)
        if not sku:
            return "skipped"

        qty = self._extract_quantity(row)
        if qty is None:
            return "skipped"

        product = self.product_repo.get_by_sku(sku)
        if not product:
            return "unmatched"

        # Upsert inventory (duplicate rule: last row wins via order processing)
        update = InventoryUpdate(stock_doc=qty)
        self.inventory_repo.upsert(product.id, update)
        processed_skus.add(sku)

        return "upserted"

    def _extract_sku(self, row: dict[str, Any]) -> str | None:
        value = _get_row_value_case_insensitive(
            row, ["sku", "артикул", "арт.", "код", "code"]
        )
        if value is None:
            return None

        s = str(value).strip()
        if s and s.lower() not in ("none", "nan", ""):
            return s
        return None

    def _extract_quantity(self, row: dict[str, Any]) -> float | None:
        value = _get_row_value_case_insensitive(
            row, ["quantity", "количество", "остаток", "qty", "stock", "наличие", "1с"]
        )
        if value is not None:
            return self._normalize_qty(value)
        return None

    def _normalize_qty(self, value: Any) -> float | None:
        if isinstance(value, (int, float)):
            qty = float(value)
            return qty if qty >= 0 else None

        if isinstance(value, str):
            cleaned = value.strip()
            if cleaned.upper() in {"#N/A", "N/A", "NONE", "NAN", ""}:
                return None

            cleaned = cleaned.replace(" ", "").replace("\xa0", "").replace(",", ".")
            try:
                qty = float(cleaned)
                return qty if qty >= 0 else None
            except ValueError:
                return None

        return None
