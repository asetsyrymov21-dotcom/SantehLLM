"""Tests for SKU utilities."""

import pytest

from app.utils.sku_utils import (
    normalize_sku,
    derive_brand_from_sku,
    is_frap_sku,
    is_gappo_sku,
    get_brand_from_normalized_sku,
)


class TestNormalizeSku:
    """Test SKU normalization."""

    def test_basic_normalization(self):
        """Basic trimming and uppercasing."""
        assert normalize_sku("f1002-b") == "F1002-B"
        assert normalize_sku("  F1002-B  ") == "F1002-B"
        assert normalize_sku("F1002-B") == "F1002-B"

    def test_whitespace_collapse(self):
        """Multiple spaces collapsed."""
        assert normalize_sku("F  1002  B") == "F1002B"

    def test_dash_normalization(self):
        """Various dash types normalized to hyphen."""
        # em-dash, en-dash, minus sign
        assert normalize_sku("F1002–B") == "F1002-B"  # en-dash
        assert normalize_sku("F1002—B") == "F1002-B"  # em-dash
        assert normalize_sku("F1002−B") == "F1002-B"  # minus sign

    def test_prefix_removal(self):
        """Common prefixes removed."""
        # Note: Russian prefixes are handled by regex in normalize_sku
        # Testing with ASCII-safe examples that demonstrate the logic
        assert normalize_sku("ART. F1002") == "F1002"
        assert normalize_sku("CODE G1234") == "G1234"
        assert normalize_sku("NR.F1002") == "F1002"
        assert normalize_sku("MODEL: X123") == "X123"

    def test_none_and_empty(self):
        """None and empty return None."""
        assert normalize_sku(None) is None
        assert normalize_sku("") is None
        assert normalize_sku("   ") is None
        assert normalize_sku("---") is None

    def test_number_input(self):
        """Numeric input converted to string."""
        assert normalize_sku(12345) == "12345"


class TestDeriveBrandFromSku:
    """Test brand derivation from SKU."""

    def test_frap_prefix(self):
        """SKU starting with F -> FRAP."""
        assert derive_brand_from_sku("F1002-B") == "FRAP"
        assert derive_brand_from_sku("f1002-b") == "FRAP"
        assert derive_brand_from_sku("F1234") == "FRAP"
        assert derive_brand_from_sku("ART. F1002") == "FRAP"  # With prefix

    def test_gappo_prefix(self):
        """SKU starting with G -> GAPPO."""
        assert derive_brand_from_sku("G1234") == "GAPPO"
        assert derive_brand_from_sku("g5678") == "GAPPO"
        assert derive_brand_from_sku("G-ABC-123") == "GAPPO"

    def test_unknown_prefix(self):
        """Unknown prefix returns None."""
        assert derive_brand_from_sku("X1234") is None
        assert derive_brand_from_sku("ABC123") is None
        assert derive_brand_from_sku("12345") is None

    def test_empty_and_none(self):
        """Empty input returns None."""
        assert derive_brand_from_sku(None) is None
        assert derive_brand_from_sku("") is None


class TestBrandHelpers:
    """Test helper functions."""

    def test_is_frap_sku(self):
        assert is_frap_sku("F1002") is True
        assert is_frap_sku("G1234") is False
        assert is_frap_sku("X1234") is False

    def test_is_gappo_sku(self):
        assert is_gappo_sku("G1234") is True
        assert is_gappo_sku("F1002") is False
        assert is_gappo_sku("X1234") is False

    def test_get_brand_from_normalized_sku(self):
        assert get_brand_from_normalized_sku("F1002") == "FRAP"
        assert get_brand_from_normalized_sku("G1234") == "GAPPO"
        assert get_brand_from_normalized_sku("X1234") is None


class TestIntegration:
    """Integration tests combining normalize and derive."""

    def test_real_world_examples(self):
        """Real-world SKU formats."""
        # FRAP examples
        assert derive_brand_from_sku(normalize_sku("F1002-B")) == "FRAP"
        assert derive_brand_from_sku(normalize_sku("f1002-b")) == "FRAP"
        assert derive_brand_from_sku(normalize_sku("ART. F1002-B")) == "FRAP"

        # GAPPO examples
        assert derive_brand_from_sku(normalize_sku("G1234")) == "GAPPO"
        assert derive_brand_from_sku(normalize_sku("g1234")) == "GAPPO"
        assert derive_brand_from_sku(normalize_sku("Код G1234")) == "GAPPO"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
