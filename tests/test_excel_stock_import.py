"""Regression tests for Excel stock import pipeline."""

import pytest
from unittest.mock import Mock

from app.services.product_import.stock_import_service import (
    StockImportService,
    StockImportResult,
)


class TestStockImportService:
    """Stock import matching by SKU."""

    def test_valid_sku_updates_inventory(self):
        """Stock row with valid SKU updates inventory."""
        mock_session = Mock()
        service = StockImportService(mock_session)

        mock_product = Mock()
        mock_product.id = 123
        mock_product.sku = "F1002-B"
        service.product_repo = Mock()
        service.product_repo.get_by_sku = Mock(return_value=mock_product)

        service.inventory_repo = Mock()
        service.inventory_repo.upsert = Mock(return_value=Mock())

        row = {"sku": "F1002-B", "quantity": 50}
        result = service._process_single_row(row, set())

        assert result == "upserted"
        service.inventory_repo.upsert.assert_called_once()

    def test_unknown_sku_goes_to_unmatched(self):
        """Unknown SKU doesn't break import, goes to unmatched."""
        mock_session = Mock()
        service = StockImportService(mock_session)

        service.product_repo = Mock()
        service.product_repo.get_by_sku = Mock(return_value=None)

        row = {"sku": "UNKNOWN-999", "quantity": 50}
        result = service._process_single_row(row, set())

        assert result == "unmatched"

    def test_missing_quantity_goes_to_skipped(self):
        """Row without quantity is skipped, not failed."""
        mock_session = Mock()
        service = StockImportService(mock_session)

        row = {"sku": "F1002-B"}  # No quantity
        result = service._process_single_row(row, set())

        assert result == "skipped"

    def test_invalid_quantity_goes_to_skipped(self):
        """Non-numeric quantity is skipped."""
        mock_session = Mock()
        service = StockImportService(mock_session)

        row = {"sku": "F1002-B", "quantity": "not-a-number"}
        result = service._process_single_row(row, set())

        assert result == "skipped"

    def test_negative_quantity_goes_to_skipped(self):
        """Negative quantity is skipped."""
        mock_session = Mock()
        service = StockImportService(mock_session)

        row = {"sku": "F1002-B", "quantity": -5}
        result = service._process_single_row(row, set())

        assert result == "skipped"

    def test_quantity_parsing_variants(self):
        """Various quantity formats parsed correctly."""
        service = StockImportService(Mock())

        assert service._normalize_qty(50) == 50.0
        assert service._normalize_qty("50") == 50.0
        assert service._normalize_qty("1 234") == 1234.0
        assert service._normalize_qty("12.5") == 12.5
        assert service._normalize_qty("12,5") == 12.5
        assert service._normalize_qty("-5") is None
        assert service._normalize_qty("abc") is None
        assert service._normalize_qty(None) is None


class TestDuplicateSkuHandling:
    """Duplicate SKU rule: last row wins."""

    def test_duplicate_sku_last_row_wins(self):
        """When same SKU appears multiple times, last value is used."""
        mock_session = Mock()
        service = StockImportService(mock_session)

        mock_product = Mock()
        mock_product.id = 123
        service.product_repo = Mock()
        service.product_repo.get_by_sku = Mock(return_value=mock_product)

        service.inventory_repo = Mock()
        service.inventory_repo.upsert = Mock(return_value=Mock())

        # Two rows with same SKU, different quantities
        rows = [
            {"sku": "F1002-B", "quantity": 10},
            {"sku": "F1002-B", "quantity": 50},  # This should win
        ]

        result = service.import_stock_rows(rows)

        assert result.upserted == 2  # Both processed
        assert result.matched == 2

        # Last call should have quantity 50
        calls = service.inventory_repo.upsert.call_args_list
        assert len(calls) == 2
        # Check last call has qty 50
        last_update = calls[-1][0][1]  # second positional arg is InventoryUpdate
        assert last_update.stock_doc == 50


class TestStockImportResultAggregation:
    """Summary counts are correct."""

    def test_import_counts(self):
        mock_session = Mock()
        service = StockImportService(mock_session)

        def side_effect(row, processed):
            sku = row.get("sku")
            if sku == "A":
                return "upserted"
            elif sku == "B":
                return "upserted"
            elif sku == "UNKNOWN":
                return "unmatched"
            elif sku == "NO-QTY":
                return "skipped"
            else:
                raise ValueError("fail")

        service._process_single_row = Mock(side_effect=side_effect)

        rows = [
            {"sku": "A", "qty": 1},
            {"sku": "B", "qty": 2},
            {"sku": "UNKNOWN", "qty": 3},
            {"sku": "NO-QTY"},
            {"sku": "FAIL", "qty": 5},
        ]

        result = service.import_stock_rows(rows)

        assert result.total_received == 5
        assert result.upserted == 2
        assert result.matched == 2
        assert result.unmatched == 1
        assert result.skipped == 1
        assert result.failed == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])