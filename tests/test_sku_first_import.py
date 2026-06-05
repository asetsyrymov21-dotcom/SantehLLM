"""Tests for SKU-first product import with PDF enrichment flagging.

These tests verify the requirements:
1. Product identity based only on SKU
2. Import with only SKU + price (title optional, name falls back to SKU)
3. Missing description does NOT cause skip
4. needs_pdf_enrichment=true when metadata insufficient
5. Engineering SKUs (F101.2004) are imported
6. Schema remains strict outside import path
"""

import pytest
from pydantic import ValidationError

from app.services.product_import.merge_service import (
    MergeService,
    _is_engineering_sku,
    _is_weak_title,
    _is_weak_description,
)
from app.services.product_import.product_persistence_service import (
    _resolve_product_name,
    _convert_to_product_create,
)
from app.schemas.product import ProductCreate


class TestEngineeringSkuDetection:
    """Engineering SKUs can still be identified for diagnostics."""

    @pytest.mark.parametrize(
        "sku,expected",
        [
            ("F101.2004", True),  # Engineering pattern
            ("F201.1503", True),  # Engineering pattern
            ("F1002-B", False),  # Regular SKU
            ("F2002", False),  # Regular SKU
            ("GAPPO-G1001", False),  # Regular SKU
            (None, False),  # No SKU
            ("", False),  # Empty SKU
        ],
    )
    def test_engineering_sku_detection(self, sku, expected):
        assert _is_engineering_sku(sku) == expected


class TestWeakTitleDetection:
    """Weak titles should trigger PDF enrichment."""

    @pytest.mark.parametrize(
        "title,expected_weak",
        [
            (None, True),  # Missing title
            ("", True),  # Empty title
            ("F1002", True),  # Just SKU-like
            ("F1002-B", True),  # Just SKU
            ("AB12", True),  # Too short
            ("F1002-B (смес. хром. д/раковины ф40)", False),  # Good title
            ("GAPPO Modern Kitchen Faucet", False),  # Good title
            ("Tiny", True),  # Too short (< 5 chars)
        ],
    )
    def test_weak_title_detection(self, title, expected_weak):
        assert _is_weak_title(title) == expected_weak


class TestWeakDescriptionDetection:
    """Weak descriptions should trigger PDF enrichment."""

    @pytest.mark.parametrize(
        "desc,expected_weak",
        [
            (None, True),  # Missing description
            ("", True),  # Empty description
            ("Short", True),  # Too short
            ("Good description here", False),  # Sufficient description
            ("Смеситель для раковины с керамическим картриджем.", False),  # Good desc
        ],
    )
    def test_weak_description_detection(self, desc, expected_weak):
        assert _is_weak_description(desc) == expected_weak


class TestNameFallbackLogic:
    """Local name fallback logic for Excel import path only."""

    def test_name_fallback_when_title_present(self):
        """When Excel title is present, use it as name."""
        name, used_fallback = _resolve_product_name("GAPPO Kitchen Mixer", "F1002-B")
        assert name == "GAPPO Kitchen Mixer"
        assert used_fallback is False

    def test_name_fallback_when_title_empty(self):
        """When Excel title is empty, fallback to SKU."""
        name, used_fallback = _resolve_product_name("", "F1002-B")
        assert name == "F1002-B"
        assert used_fallback is True

    def test_name_fallback_when_title_none(self):
        """When Excel title is None, fallback to SKU."""
        name, used_fallback = _resolve_product_name(None, "F1002-B")
        assert name == "F1002-B"
        assert used_fallback is True

    def test_name_fallback_when_title_whitespace(self):
        """When Excel title is whitespace only, fallback to SKU."""
        name, used_fallback = _resolve_product_name("   ", "F1002-B")
        assert name == "F1002-B"
        assert used_fallback is True

    def test_convert_to_product_create_with_fallback(self):
        """ProductCreate gets name=SKU when title missing."""
        built_product = {
            "sku": "F1002-B",
            "title": None,  # No title
            "price": 9520.0,
            "currency": "KZT",
            "base_attributes": {"needs_pdf_enrichment": True},
        }

        product_create = _convert_to_product_create(built_product)

        assert product_create.sku == "F1002-B"
        assert product_create.name == "F1002-B"  # Fallback to SKU
        assert product_create.attributes_json["needs_pdf_enrichment"] is True

    def test_convert_to_product_create_with_title(self):
        """ProductCreate gets name=title when title present."""
        built_product = {
            "sku": "F1002-B",
            "title": "GAPPO Kitchen Mixer Chrome",
            "price": 9520.0,
            "currency": "KZT",
            "base_attributes": {},
        }

        product_create = _convert_to_product_create(built_product)

        assert product_create.sku == "F1002-B"
        assert product_create.name == "GAPPO Kitchen Mixer Chrome"


class TestSchemaStrictnessOutsideImportPath:
    """Verify ProductCreate schema remains strict globally."""

    def test_product_create_requires_name(self):
        """ProductCreate requires name field at schema level."""
        with pytest.raises(ValidationError) as exc_info:
            ProductCreate(
                sku="F1002-B",
                # name is missing - should fail
                price=9520.0,
            )

        assert "name" in str(exc_info.value)

    def test_product_create_requires_sku(self):
        """ProductCreate requires sku field at schema level."""
        with pytest.raises(ValidationError) as exc_info:
            ProductCreate(
                name="Test Product",
                # sku is missing - should fail
                price=9520.0,
            )

        assert "sku" in str(exc_info.value)

    def test_product_create_accepts_valid_data(self):
        """ProductCreate accepts valid complete data."""
        product = ProductCreate(
            sku="F1002-B",
            name="GAPPO Kitchen Mixer",
            price=9520.0,
            currency="KZT",
        )

        assert product.sku == "F1002-B"
        assert product.name == "GAPPO Kitchen Mixer"
        assert product.price == 9520.0


class TestSkuFirstProductBuilding:
    """SKU-first product building with enrichment flagging."""

    def test_import_with_only_sku_and_price(self):
        """Requirement: Import even with only SKU + price."""
        service = MergeService()
        excel_row = {
            "sku": "F1002-B",
            "title": None,
            "price": 9520.0,
            "discount_price": None,
            "stock_qty": None,
            "currency": "KZT",
            "base_attributes": {},
            "source_file": "test.xlsx",
            "source_sheet": "Sheet1",
            "source_row_index": 0,
        }

        product = service.build_product_from_excel(excel_row)

        assert product["sku"] == "F1002-B"
        assert product["price"] == 9520.0
        # Title is None (will use SKU fallback for name)
        assert product["title"] is None
        # Must need enrichment
        assert product["base_attributes"]["needs_pdf_enrichment"] is True
        assert product["base_attributes"]["description_missing_in_excel"] is True

    def test_import_with_sku_price_and_title(self):
        """Import with SKU + price + good title - no enrichment needed."""
        service = MergeService()
        excel_row = {
            "sku": "F1002-B",
            "title": "F1002-B (смес. хром. д/раковины ф40)",
            "price": 9520.0,
            "discount_price": None,
            "stock_qty": None,
            "currency": "KZT",
            "base_attributes": {},
            "source_file": "test.xlsx",
            "source_sheet": "Sheet1",
            "source_row_index": 0,
        }

        product = service.build_product_from_excel(excel_row)

        assert product["sku"] == "F1002-B"
        assert product["title"] == "F1002-B (смес. хром. д/раковины ф40)"
        assert product["price"] == 9520.0
        # Good title present -> NO enrichment needed (even without description)
        assert product["base_attributes"]["needs_pdf_enrichment"] is False
        # But we still track that description was missing
        assert product["base_attributes"]["description_missing_in_excel"] is True

    def test_import_with_full_metadata_no_enrichment_needed(self):
        """Import with complete metadata - no enrichment needed."""
        service = MergeService()
        excel_row = {
            "sku": "F1002-B",
            "title": "F1002-B (смес. хром. д/раковины ф40)",
            "price": 9520.0,
            "discount_price": None,
            "stock_qty": None,
            "currency": "KZT",
            "description": "Смеситель для раковины с керамическим картриджем. Хромированная поверхность.",
            "base_attributes": {},
            "source_file": "test.xlsx",
            "source_sheet": "Sheet1",
            "source_row_index": 0,
        }

        product = service.build_product_from_excel(excel_row)

        assert product["sku"] == "F1002-B"
        # Both title and description present -> no enrichment needed
        assert product["base_attributes"]["needs_pdf_enrichment"] is False
        assert "description_missing_in_excel" not in product["base_attributes"]

    def test_engineering_sku_is_imported(self):
        """Engineering SKUs like F101.2004 should be imported."""
        service = MergeService()
        excel_row = {
            "sku": "F101.2004",
            "title": "Some engineering product",
            "price": 50000.0,
            "currency": "KZT",
            "base_attributes": {},
            "source_file": "test.xlsx",
            "source_sheet": "Sheet1",
            "source_row_index": 0,
        }

        product = service.build_product_from_excel(excel_row)

        assert product["sku"] == "F101.2004"
        assert product["title"] == "Some engineering product"
        assert product["price"] == 50000.0
        assert product["merge_status"] == "excel_only"
        assert "_skipped_reason" not in product["base_attributes"]

    def test_title_saved_when_present(self):
        """Excel short name/title should be saved when present."""
        service = MergeService()
        excel_row = {
            "sku": "F3001",
            "title": "GAPPO Kitchen Mixer Chrome",
            "price": 15000.0,
            "currency": "KZT",
            "base_attributes": {},
            "source_file": "test.xlsx",
            "source_sheet": "Sheet1",
            "source_row_index": 0,
        }

        product = service.build_product_from_excel(excel_row)

        assert product["title"] == "GAPPO Kitchen Mixer Chrome"

    def test_category_extracted_from_name(self):
        """Category should be extracted from product name when possible."""
        service = MergeService()
        excel_row = {
            "sku": "F1002-B",
            "title": "F1002-B (смес. хром. д/раковины ф40)",
            "price": 9520.0,
            "currency": "KZT",
            "base_attributes": {},
            "source_file": "test.xlsx",
            "source_sheet": "Sheet1",
            "source_row_index": 0,
        }

        product = service.build_product_from_excel(excel_row)

        assert product["category"] == "смеситель"

    def test_no_category_when_name_unclear(self):
        """Category should be None when name doesn't indicate category."""
        service = MergeService()
        excel_row = {
            "sku": "X1234",
            "title": "Some random accessory",
            "price": 500.0,
            "currency": "KZT",
            "base_attributes": {},
            "source_file": "test.xlsx",
            "source_sheet": "Sheet1",
            "source_row_index": 0,
        }

        product = service.build_product_from_excel(excel_row)

        assert product["category"] is None


class TestAttributeExtractionIntegration:
    """Attribute extraction from product names."""

    def test_diameter_extracted_from_name(self):
        service = MergeService()
        excel_row = {
            "sku": "F1002-B",
            "title": "F1002-B (смес. хром. д/раковины ф40)",
            "price": 9520.0,
            "currency": "KZT",
            "base_attributes": {},
            "source_file": "test.xlsx",
            "source_sheet": "Sheet1",
            "source_row_index": 0,
        }

        product = service.build_product_from_excel(excel_row)

        assert product["base_attributes"]["diameter_mm"] == 40
        assert product["base_attributes"]["finish"] == "хром"
        assert product["base_attributes"]["application"] == "раковина"

    def test_spout_and_diverter_extracted(self):
        service = MergeService()
        excel_row = {
            "sku": "F2102-B",
            "title": "F2102-B (смес. хром. д/ван. Ф40. излив 30S переключение душ - дивертор/картридж)",
            "price": 17230.0,
            "currency": "KZT",
            "base_attributes": {},
            "source_file": "test.xlsx",
            "source_sheet": "Sheet1",
            "source_row_index": 0,
        }

        product = service.build_product_from_excel(excel_row)

        assert product["base_attributes"]["spout"] == "30S"
        assert product["base_attributes"]["switch_type"] == "дивертор"
        assert product["base_attributes"]["cartridge"] is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
