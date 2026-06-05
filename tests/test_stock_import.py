"""Tests for stock import service."""

import pytest
from unittest.mock import Mock, MagicMock

from app.services.stock_import import StockExcelParser, StockMatcher, StockImporter
from app.services.stock_import.excel_parser import ExcelStockRow
from app.api.imports import _parse_stock_excel_file, StockQuantityColumnMissingError


class TestStockExcelParser:
    """Test Excel parsing logic."""

    def test_find_column_mapping_article(self):
        """Must find article column."""
        from app.services.stock_import.excel_parser import find_column_mapping

        headers = ["Артикул", "Название", "Остаток"]
        mapping = find_column_mapping(headers)
        assert "article" in mapping
        assert mapping["article"] == "Артикул"

    def test_find_column_mapping_quantity(self):
        """Should find quantity column."""
        from app.services.stock_import.excel_parser import find_column_mapping

        headers = ["Артикул", "Шт", "Цена"]
        mapping = find_column_mapping(headers)
        assert "quantity" in mapping
        assert mapping["quantity"] == "Шт"

    def test_find_column_mapping_fuzzy_headers(self):
        """Should tolerate common supplier header wording changes."""
        from app.services.stock_import.excel_parser import find_column_mapping

        headers = ["Артикул поставщика", "Свободный остаток, шт.", "Цена со скидкой"]
        mapping = find_column_mapping(headers)
        assert mapping["article"] == "Артикул поставщика"
        assert mapping["quantity"] == "Свободный остаток, шт."

    def test_find_column_mapping_does_not_treat_price_as_quantity(self):
        """Price columns must not be used as stock quantity."""
        from app.services.stock_import.excel_parser import find_column_mapping

        headers = ["Артикул", "Наименование", "РРЦ", "Цена со скидкой"]
        mapping = find_column_mapping(headers)
        assert mapping["article"] == "Артикул"
        assert "quantity" not in mapping

    def test_find_column_mapping_missing_article(self):
        """Should raise error if no article column."""
        from app.services.stock_import.excel_parser import find_column_mapping

        headers = ["Название", "Цена", "Описание"]
        with pytest.raises(ValueError, match="article"):
            find_column_mapping(headers)

    def test_auto_header_detects_stock_file_after_service_rows(self, tmp_path):
        """Stock files may have advertising/service rows before real headers."""
        from openpyxl import Workbook

        file_path = tmp_path / "stock.xlsx"
        wb = Workbook()
        ws = wb.active
        ws.append(["", "2026", "", ""])
        ws.append(["", "ПРАЙС ЛИСТ", "", ""])
        ws.append(["Артикул", "Название", "Остаток", "Цена"])
        ws.append(["F1002-B", "Смеситель", None, 9520])
        ws.append(["F2002-B", "Смеситель", "7", 12230])
        wb.save(file_path)

        result = _parse_stock_excel_file(str(file_path))

        assert result.column_mapping["article"] == "Артикул"
        assert result.column_mapping["quantity"] == "Остаток"
        assert len(result.rows) == 2
        assert result.rows[0].raw_quantity is None
        assert result.rows[1].raw_quantity == "7"

    def test_price_file_without_stock_column_is_rejected(self, tmp_path):
        """A catalog price list must not be imported as zero stock."""
        from openpyxl import Workbook

        file_path = tmp_path / "price.xlsx"
        wb = Workbook()
        ws = wb.active
        ws.append(["", "2026", "", ""])
        ws.append(["", "ПРАЙС ЛИСТ", "", ""])
        ws.append(["Артикул", "Название", "Розница", "ОПТ"])
        ws.append(["F1002-B", "Смеситель", 9520, 7140])
        ws.append(["F2002-B", "Смеситель", 12230, 9180])
        wb.save(file_path)

        with pytest.raises(StockQuantityColumnMissingError, match="прайс-лист"):
            _parse_stock_excel_file(str(file_path))

    def test_header_detection_continues_after_article_only_row(self, tmp_path):
        """An article-only candidate should not block a later real stock header."""
        from openpyxl import Workbook

        file_path = tmp_path / "mixed.xlsx"
        wb = Workbook()
        ws = wb.active
        ws.append(["", "ПРАЙС ЛИСТ", "", ""])
        ws.append(["Артикул", "Наименование", "РРЦ", "Цена со скидкой"])
        ws.append(["F1002-B", "Смеситель", 9520, 7140])
        ws.append(["Артикул поставщика", "Свободный остаток, шт.", "Цена"])
        ws.append(["F2002-B", "12", 12230])
        wb.save(file_path)

        result = _parse_stock_excel_file(str(file_path))

        assert result.column_mapping["article"] == "Артикул поставщика"
        assert result.column_mapping["quantity"] == "Свободный остаток, шт."
        assert len(result.rows) == 1
        assert result.rows[0].raw_article == "F2002-B"
        assert result.rows[0].raw_quantity == "12"


class TestStockMatcher:
    """Test matching logic."""

    def test_frap_sku_matched(self):
        """FRAP SKU should match when product exists."""
        mock_session = Mock()
        matcher = StockMatcher(mock_session, brand_filter=None)

        # Mock product repo
        mock_product = Mock()
        mock_product.id = 123
        mock_product.brand = "FRAP"
        matcher.product_repo = Mock()
        matcher.product_repo.get_by_sku = Mock(return_value=mock_product)

        row = ExcelStockRow(
            raw_article="F1002-B",
            raw_quantity="10",
            row_index=1,
            source_file="test.xlsx",
            raw_data={},
        )

        result = matcher._match_single_row(row)

        assert result.match_status == "matched"
        assert result.product_id == 123
        assert result.brand_derived == "FRAP"

    def test_gappo_sku_matched(self):
        """GAPPO SKU should match when product exists in multi-brand mode."""
        mock_session = Mock()
        matcher = StockMatcher(mock_session, brand_filter=None)

        # Mock product repo
        mock_product = Mock()
        mock_product.id = 456
        mock_product.brand = "GAPPO"
        matcher.product_repo = Mock()
        matcher.product_repo.get_by_sku = Mock(return_value=mock_product)

        row = ExcelStockRow(
            raw_article="G1234",
            raw_quantity="10",
            row_index=1,
            source_file="test.xlsx",
            raw_data={},
        )

        result = matcher._match_single_row(row)

        assert result.match_status == "matched"
        assert result.product_id == 456
        assert result.brand_derived == "GAPPO"

    def test_gappo_sku_skipped_in_legacy_frap_mode(self):
        """GAPPO SKU should be skipped in legacy FRAP-only mode."""
        mock_session = Mock()
        matcher = StockMatcher(mock_session, brand_filter={"FRAP"})

        row = ExcelStockRow(
            raw_article="G1234",
            raw_quantity="10",
            row_index=1,
            source_file="test.xlsx",
            raw_data={},
        )

        result = matcher._match_single_row(row)

        assert result.match_status == "unsupported_brand"
        assert result.brand_derived == "GAPPO"

    def test_unsupported_brand_skipped(self):
        """X1234 should be skipped as unsupported brand."""
        mock_session = Mock()
        matcher = StockMatcher(mock_session, brand_filter=None)

        row = ExcelStockRow(
            raw_article="X1234",
            raw_quantity="10",
            row_index=1,
            source_file="test.xlsx",
            raw_data={},
        )

        result = matcher._match_single_row(row)

        assert result.match_status == "unsupported_brand"
        assert result.brand_derived is None

    def test_unknown_sku_unmatched(self):
        """Unknown SKU returns unmatched."""
        mock_session = Mock()
        matcher = StockMatcher(mock_session, brand_filter="FRAP")

        matcher.product_repo = Mock()
        matcher.product_repo.get_by_sku = Mock(return_value=None)

        row = ExcelStockRow(
            raw_article="F99999",
            raw_quantity="10",
            row_index=1,
            source_file="test.xlsx",
            raw_data={},
        )

        result = matcher._match_single_row(row)

        assert result.match_status == "unmatched"

    def test_empty_sku_invalid(self):
        """Empty SKU returns invalid."""
        mock_session = Mock()
        matcher = StockMatcher(mock_session, brand_filter="FRAP")

        row = ExcelStockRow(
            raw_article="",
            raw_quantity="10",
            row_index=1,
            source_file="test.xlsx",
            raw_data={},
        )

        result = matcher._match_single_row(row)

        assert result.match_status == "invalid_sku"

    def test_plus_quantity_parsed(self):
        """10+ quantity should be parsed correctly."""
        mock_session = Mock()
        matcher = StockMatcher(mock_session, brand_filter="FRAP")

        mock_product = Mock()
        mock_product.id = 123
        mock_product.brand = "FRAP"
        matcher.product_repo = Mock()
        matcher.product_repo.get_by_sku = Mock(return_value=mock_product)

        row = ExcelStockRow(
            raw_article="F1002",
            raw_quantity="10+",
            row_index=1,
            source_file="test.xlsx",
            raw_data={},
        )

        result = matcher._match_single_row(row)

        assert result.match_status == "matched"
        assert result.parsed_qty.parse_status == "range_plus"
        assert result.parsed_qty.stock_min == 10


class TestEmptyQtyParsing:
    """Test empty quantity handling - treated as 0, not invalid."""

    def test_empty_qty_string_matched_as_zero(self):
        """Empty string qty should be matched with qty=0."""
        mock_session = Mock()
        matcher = StockMatcher(mock_session, brand_filter="FRAP")

        mock_product = Mock()
        mock_product.id = 123
        mock_product.brand = "FRAP"
        matcher.product_repo = Mock()
        matcher.product_repo.get_by_sku = Mock(return_value=mock_product)

        row = ExcelStockRow(
            raw_article="F1002",
            raw_quantity="",
            row_index=1,
            source_file="test.xlsx",
            raw_data={},
        )

        result = matcher._match_single_row(row)

        assert result.match_status == "matched"
        assert result.parsed_qty.parse_status == "empty"
        assert result.parsed_qty.stock_exact == 0
        assert result.parsed_qty.stock_min == 0

    def test_whitespace_only_qty_matched_as_zero(self):
        """Whitespace-only qty should be matched with qty=0."""
        mock_session = Mock()
        matcher = StockMatcher(mock_session, brand_filter="FRAP")

        mock_product = Mock()
        mock_product.id = 123
        mock_product.brand = "FRAP"
        matcher.product_repo = Mock()
        matcher.product_repo.get_by_sku = Mock(return_value=mock_product)

        row = ExcelStockRow(
            raw_article="F1002",
            raw_quantity="   ",
            row_index=1,
            source_file="test.xlsx",
            raw_data={},
        )

        result = matcher._match_single_row(row)

        assert result.match_status == "matched"
        assert result.parsed_qty.parse_status == "empty"
        assert result.parsed_qty.stock_exact == 0

    def test_none_qty_matched_as_zero(self):
        """None qty should be matched with qty=0."""
        mock_session = Mock()
        matcher = StockMatcher(mock_session, brand_filter="FRAP")

        mock_product = Mock()
        mock_product.id = 123
        mock_product.brand = "FRAP"
        matcher.product_repo = Mock()
        matcher.product_repo.get_by_sku = Mock(return_value=mock_product)

        row = ExcelStockRow(
            raw_article="F1002",
            raw_quantity=None,
            row_index=1,
            source_file="test.xlsx",
            raw_data={},
        )

        result = matcher._match_single_row(row)

        assert result.match_status == "matched"
        assert result.parsed_qty.parse_status == "empty"
        assert result.parsed_qty.stock_exact == 0

    def test_excel_ref_error_is_invalid(self):
        """Excel #REF! error should be invalid_qty, not empty."""
        mock_session = Mock()
        matcher = StockMatcher(mock_session, brand_filter="FRAP")

        row = ExcelStockRow(
            raw_article="F1002",
            raw_quantity="#REF!",
            row_index=1,
            source_file="test.xlsx",
            raw_data={},
        )

        result = matcher._match_single_row(row)

        assert result.match_status == "invalid_qty"
        assert result.parsed_qty.parse_status == "invalid"

    def test_excel_na_error_is_invalid(self):
        """Excel #N/A error should be invalid_qty, not empty."""
        mock_session = Mock()
        matcher = StockMatcher(mock_session, brand_filter="FRAP")

        row = ExcelStockRow(
            raw_article="F1002",
            raw_quantity="#N/A",
            row_index=1,
            source_file="test.xlsx",
            raw_data={},
        )

        result = matcher._match_single_row(row)

        assert result.match_status == "invalid_qty"
        assert result.parsed_qty.parse_status == "invalid"

    def test_excel_error_lowercase_is_invalid(self):
        """Excel #error! (lowercase) should be invalid_qty."""
        mock_session = Mock()
        matcher = StockMatcher(mock_session, brand_filter="FRAP")

        row = ExcelStockRow(
            raw_article="F1002",
            raw_quantity="#error!",
            row_index=1,
            source_file="test.xlsx",
            raw_data={},
        )

        result = matcher._match_single_row(row)

        assert result.match_status == "invalid_qty"
        assert result.parsed_qty.parse_status == "invalid"


class TestMatchReport:
    """Test report generation."""

    def test_duplicate_detection(self):
        """Duplicate SKUs should be tracked."""
        mock_session = Mock()
        matcher = StockMatcher(mock_session, brand_filter="FRAP")

        mock_product = Mock()
        mock_product.id = 123
        mock_product.brand = "FRAP"
        matcher.product_repo = Mock()
        matcher.product_repo.get_by_sku = Mock(return_value=mock_product)

        rows = [
            ExcelStockRow(
                raw_article="F1002",
                raw_quantity="10",
                row_index=1,
                source_file="test.xlsx",
                raw_data={},
            ),
            ExcelStockRow(
                raw_article="F1002",
                raw_quantity="20",
                row_index=2,
                source_file="test.xlsx",
                raw_data={},
            ),
        ]

        report = matcher.match_rows(rows)

        assert report.duplicate_sku_in_source == 1
        assert "F1002" in report.duplicate_skus


class TestMultiBrandImport:
    """Test FRAP + GAPPO multi-brand import."""

    def test_both_brands_processed(self):
        """Importer should process both FRAP and GAPPO SKUs."""
        mock_session = Mock()
        matcher = StockMatcher(mock_session, brand_filter=None)

        # Mock product repo for both brands
        mock_frap = Mock()
        mock_frap.id = 123
        mock_frap.brand = "FRAP"

        mock_gappo = Mock()
        mock_gappo.id = 456
        mock_gappo.brand = "GAPPO"

        def mock_get_by_sku(sku):
            if sku.startswith("F"):
                return mock_frap
            elif sku.startswith("G"):
                return mock_gappo
            return None

        matcher.product_repo = Mock()
        matcher.product_repo.get_by_sku = Mock(side_effect=mock_get_by_sku)

        rows = [
            ExcelStockRow(
                raw_article="F1001",
                raw_quantity="10",
                row_index=1,
                source_file="test.xlsx",
                raw_data={},
            ),
            ExcelStockRow(
                raw_article="G2001",
                raw_quantity="20",
                row_index=2,
                source_file="test.xlsx",
                raw_data={},
            ),
            ExcelStockRow(
                raw_article="X9999",
                raw_quantity="30",
                row_index=3,
                source_file="test.xlsx",
                raw_data={},
            ),
        ]

        report = matcher.match_rows(rows)

        # Both FRAP and GAPPO should be processed
        assert report.frap_candidate_rows == 1
        assert report.gappo_candidate_rows == 1
        assert report.skipped_unsupported_brand == 1

        # Should have matches for F and G
        matched = [r for r in report.results if r.match_status == "matched"]
        assert len(matched) == 2


class TestSheetNamePropagation:
    """Test that sheet_name is properly propagated from Excel row."""

    def test_sheet_name_in_match_result(self):
        """sheet_name should be preserved in match result."""
        mock_session = Mock()
        matcher = StockMatcher(mock_session, brand_filter=None)

        mock_product = Mock()
        mock_product.id = 123
        mock_product.brand = "FRAP"
        matcher.product_repo = Mock()
        matcher.product_repo.get_by_sku = Mock(return_value=mock_product)

        row = ExcelStockRow(
            raw_article="F1002",
            raw_quantity="10",
            row_index=1,
            source_file="test.xlsx",
            sheet_name="水",
            raw_data={"__sheet_name": "水"},
        )

        result = matcher._match_single_row(row)

        assert result.sheet_name == "水"
        assert result.match_status == "matched"


class TestUnmatchedCsvExport:
    """Test unmatched CSV export includes all required fields."""

    def test_csv_includes_brand_and_sheet_name(self):
        """CSV should include brand and sheet_name fields."""
        from app.services.stock_import.matcher import MatchResult, UnmatchedSkuReport
        from app.utils.stock_parser import parse_stock_value
        from datetime import datetime

        result = MatchResult(
            row_index=1,
            raw_sku="F1234",
            normalized_sku="F1234",
            raw_qty="10",
            parsed_qty=parse_stock_value("10"),
            product_id=None,
            match_status="unmatched",
            brand_derived="FRAP",
            sheet_name="水",
            notes=["Product not found"],
        )

        report = UnmatchedSkuReport(
            unmatched_results=[result],
            generated_at=datetime.utcnow(),
        )

        report_dict = result.to_report_dict()

        assert "brand" in report_dict
        assert "sheet_name" in report_dict
        assert report_dict["brand"] == "FRAP"
        assert report_dict["sheet_name"] == "水"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
