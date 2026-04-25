"""Tests for stock value parsing - quantity parsing edge cases.

Covers:
- Empty qty => qty=0 (valid, not skipped)
- Excel errors => invalid (skipped)
- Normal numbers => parsed as before
"""

import pytest
from app.utils.stock_parser import parse_stock_value, parse_stock_value_for_update, is_excel_error


class TestIsExcelError:
    """Test Excel error detection."""

    @pytest.mark.parametrize("error_value", [
        "#REF!",
        "#N/A",
        "#ERROR!",
        "#VALUE!",
        "#DIV/0!",
        "#NAME?",
        "#NULL!",
        "#NUM!",
        "#ref!",
        "#n/a",
        "#Error!",
    ])
    def test_excel_errors_detected(self, error_value):
        assert is_excel_error(error_value) is True

    @pytest.mark.parametrize("valid_value", [
        "",
        "   ",
        "10",
        "0",
        "10+",
        "N/A",
        "error",
        "REF",
        "#REF",
    ])
    def test_non_errors_not_detected(self, valid_value):
        assert is_excel_error(valid_value) is False


class TestEmptyQtyParsing:
    """Test that empty qty is treated as 0, not invalid."""

    def test_none_returns_empty_with_zero(self):
        result = parse_stock_value(None)
        assert result.parse_status == "empty"
        assert result.stock_exact == 0
        assert result.stock_min == 0

    def test_empty_string_returns_empty_with_zero(self):
        result = parse_stock_value("")
        assert result.parse_status == "empty"
        assert result.stock_exact == 0
        assert result.stock_min == 0

    def test_whitespace_only_returns_empty_with_zero(self):
        result = parse_stock_value("   ")
        assert result.parse_status == "empty"
        assert result.stock_exact == 0
        assert result.stock_min == 0


class TestExcelErrorParsing:
    """Test that Excel errors are treated as invalid."""

    def test_ref_error_is_invalid(self):
        result = parse_stock_value("#REF!")
        assert result.parse_status == "invalid"
        assert result.stock_exact is None
        assert result.stock_min is None

    def test_na_error_is_invalid(self):
        result = parse_stock_value("#N/A")
        assert result.parse_status == "invalid"
        assert result.stock_exact is None
        assert result.stock_min is None

    def test_error_bang_is_invalid(self):
        result = parse_stock_value("#ERROR!")
        assert result.parse_status == "invalid"
        assert result.stock_exact is None
        assert result.stock_min is None


class TestNormalQtyParsing:
    """Test that normal quantities still parse correctly."""

    def test_integer_qty(self):
        result = parse_stock_value(585)
        assert result.parse_status == "exact"
        assert result.stock_exact == 585
        assert result.stock_min == 585

    def test_integer_string_qty(self):
        result = parse_stock_value("585")
        assert result.parse_status == "exact"
        assert result.stock_exact == 585
        assert result.stock_min == 585


class TestParseStockValueForUpdate:
    """Test parse_stock_value_for_update function."""

    def test_empty_returns_zero(self):
        assert parse_stock_value_for_update("") == 0
        assert parse_stock_value_for_update(None) == 0
        assert parse_stock_value_for_update("   ") == 0

    def test_excel_error_returns_none(self):
        assert parse_stock_value_for_update("#REF!") is None
        assert parse_stock_value_for_update("#N/A") is None
        assert parse_stock_value_for_update("#ERROR!") is None

    def test_normal_number_returns_int(self):
        assert parse_stock_value_for_update(585) == 585
        assert parse_stock_value_for_update("585") == 585
        assert parse_stock_value_for_update("10+") == 10


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
