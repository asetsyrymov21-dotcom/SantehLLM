"""Minimal regression tests for Excel-first import pipeline.

Tests verify baseline behavior without database or heavy fixtures.
"""

import pytest

from app.services.product_import.excel_mapper import is_service_row
from app.services.product_import.merge_service import (
    extract_category_from_name,
    extract_attributes_from_name,
    MergeService,
)


class TestServiceRowFilter:
    """Service row detection (₸ filtering)."""

    def test_service_row_with_currency_symbol_only(self):
        row = {"sku": None, "title": None, "price": "₸"}
        assert is_service_row(row) is True

    def test_service_row_with_price_number(self):
        row = {"sku": "F1002", "title": "Test Product", "price": 9520.0}
        assert is_service_row(row) is False

    def test_service_row_empty_row(self):
        row = {"sku": None, "title": None, "price": None}
        assert is_service_row(row) is True


class TestCategoryExtraction:
    """Category parsing from product name."""

    @pytest.mark.parametrize(
        "name,expected",
        [
            ("F1002-B (смес. хром. д/раковины ф40)", "смеситель"),
            ("F2002-B (смеситель хром. д/душа ф40)", "смеситель"),
            ("Some random product", None),
            (None, None),
            ("", None),
        ],
    )
    def test_category_extraction(self, name, expected):
        assert extract_category_from_name(name) == expected


class TestAttributeExtraction:
    """Attribute parsing from product name."""

    def test_f1002_attributes(self):
        name = "F1002-B (смес. хром. д/раковины ф40)"
        attrs = extract_attributes_from_name(name)
        assert attrs["finish"] == "хром"
        assert attrs["application"] == "раковина"
        assert attrs["diameter_mm"] == 40

    def test_f2002_attributes(self):
        name = "F2002-B (смес. хром. д/душа ф40)"
        attrs = extract_attributes_from_name(name)
        assert attrs["finish"] == "хром"
        assert attrs["application"] == "душ"
        assert attrs["diameter_mm"] == 40

    def test_f2102_attributes(self):
        name = "F2102-B (смес. хром. д/ван. Ф40. излив 30S переключение душ - дивертор/картридж)"
        attrs = extract_attributes_from_name(name)
        assert attrs["finish"] == "хром"
        assert attrs["application"] == "ванна"
        assert attrs["diameter_mm"] == 40
        assert attrs["spout"] == "30S"
        assert attrs["switch_type"] == "дивертор"
        assert attrs["cartridge"] is True

    def test_diameter_not_from_sku(self):
        """Regression: diameter should come from name (ф40), not SKU."""
        # SKU F2102-B contains digits but diameter should be from ф40
        attrs = extract_attributes_from_name("F2102-B (смес. хром. ф40)")
        assert attrs["diameter_mm"] == 40

        # SKU with no diameter in name
        attrs_no_diam = extract_attributes_from_name("F2102-B (смес. хром.)")
        assert "diameter_mm" not in attrs_no_diam


class TestBuildProductFromExcel:
    """Integration: product builder with enrichment."""

    def test_product_builder_enriches_category_and_attributes(self):
        service = MergeService()
        excel_row = {
            "sku": "F2102-B",
            "title": "F2102-B (смес. хром. д/ван. Ф40. излив 30S дивертор)",
            "price": 17230.0,
            "discount_price": None,
            "stock_qty": None,
            "currency": "KZT",
            "base_attributes": {},
            "source_file": "test.xlsx",
            "source_sheet": "Sheet1",
            "source_row_index": 0,
        }

        product = service.build_product_from_excel(excel_row)

        assert product["sku"] == "F2102-B"
        assert product["category"] == "смеситель"
        assert product["currency"] == "KZT"
        assert product["base_attributes"]["diameter_mm"] == 40
        assert product["base_attributes"]["spout"] == "30S"

    def test_product_builder_preserves_existing_attributes(self):
        """Excel base_attributes should override name-derived."""
        service = MergeService()
        excel_row = {
            "sku": "TEST",
            "title": "TEST (смес. хром. ф40)",
            "price": 100.0,
            "currency": "KZT",
            "base_attributes": {"finish": "матовый", "custom_key": "value"},
        }

        product = service.build_product_from_excel(excel_row)

        # Excel finish overrides name-derived
        assert product["base_attributes"]["finish"] == "матовый"
        # Name-derived attributes still present
        assert product["base_attributes"]["diameter_mm"] == 40
        # Excel-only attributes preserved
        assert product["base_attributes"]["custom_key"] == "value"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
