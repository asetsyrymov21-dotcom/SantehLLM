"""Tests for unmatched SKU analyzer."""

import pytest
from unittest.mock import Mock, MagicMock

from app.services.stock_import.unmatched_analyzer import (
    UnmatchedSkuAnalyzer,
    SkuVariantChecker,
    UnmatchedSkuAnalysis,
)


class TestSkuVariantChecker:
    """Test SKU variant generation."""

    def test_basic_variants(self):
        checker = SkuVariantChecker()
        variants = checker.get_variants("f100.2006")  # lowercase input

        # Should generate variants
        assert len(variants) > 0

        # Check specific transforms
        assert "uppercase" in variants
        assert variants["uppercase"] == "F100.2006"

    def test_unicode_dash_transform(self):
        checker = SkuVariantChecker()
        variants = checker.get_variants("F100—2006")  # em dash

        assert "unicode_dash_to_ascii" in variants
        assert variants["unicode_dash_to_ascii"] == "F100-2006"

    def test_no_spaces_around_dash(self):
        checker = SkuVariantChecker()
        variants = checker.get_variants("F100 - 2006")

        assert "no_spaces_around_dash" in variants
        assert variants["no_spaces_around_dash"] == "F100-2006"


class TestUnmatchedSkuAnalysis:
    """Test analysis data structure."""

    def test_to_dict(self):
        analysis = UnmatchedSkuAnalysis(
            source_sku="F100.2006",
            normalized_sku="F1002006",
            source_row=42,
            qty_raw="10",
            probable_reason="format_mismatch",
            confidence="high",
            matched_catalog_sku="F100-2006",
            matched_product_id=123,
            candidate_count=1,
            notes=["Test note"],
        )

        d = analysis.to_dict()
        assert d["source_sku"] == "F100.2006"
        assert d["probable_reason"] == "format_mismatch"
        assert d["candidate_count"] == 1


class TestUnmatchedSkuAnalyzer:
    """Test analyzer logic."""

    def test_exact_recheck_finds_match(self):
        mock_session = Mock()
        analyzer = UnmatchedSkuAnalyzer(mock_session)

        # Mock product repo
        mock_product = Mock()
        mock_product.id = 123
        mock_product.sku = "F100-2006"
        analyzer.product_repo = Mock()
        analyzer.product_repo.get_by_sku = Mock(return_value=mock_product)

        result = analyzer._exact_recheck("F100-2006")

        assert result is not None
        assert result.sku == "F100-2006"

    def test_exact_recheck_no_match(self):
        mock_session = Mock()
        analyzer = UnmatchedSkuAnalyzer(mock_session)
        analyzer.product_repo = Mock()
        analyzer.product_repo.get_by_sku = Mock(return_value=None)

        result = analyzer._exact_recheck("NONEXISTENT")

        assert result is None

    def test_analyze_single_row_format_mismatch(self):
        mock_session = Mock()
        analyzer = UnmatchedSkuAnalyzer(mock_session)

        # Mock: no exact match, but format variant matches
        analyzer.product_repo = Mock()
        analyzer.product_repo.get_by_sku = Mock(
            side_effect=[
                None,  # First call - exact recheck fails
                Mock(sku="F100-2006", id=123),  # Second call - format variant succeeds
            ]
        )

        row = {
            "sku_raw": "F100.2006",
            "sku_normalized": "F1002006",
            "row": "10",
            "qty_raw": "5",
        }

        analysis = analyzer._analyze_single_row(row)

        assert analysis.probable_reason == "format_mismatch"
        assert analysis.confidence == "high"

    def test_analyze_single_row_real_missing(self):
        mock_session = Mock()
        analyzer = UnmatchedSkuAnalyzer(mock_session)

        # Mock: no matches at all
        analyzer.product_repo = Mock()
        analyzer.product_repo.get_by_sku = Mock(return_value=None)
        analyzer._get_all_frap_products = Mock(return_value=[])

        row = {
            "sku_raw": "ZZZ999",
            "sku_normalized": "ZZZ999",
            "row": "20",
            "qty_raw": "10",
        }

        analysis = analyzer._analyze_single_row(row)

        assert analysis.probable_reason == "real_missing"
        assert analysis.confidence == "medium"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
