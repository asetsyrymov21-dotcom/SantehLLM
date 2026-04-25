from types import SimpleNamespace

import pytest

from app.services.stock_import.matcher import StockMatcher
from app.utils.stock_parser import parse_stock_value


class DummyProductRepo:
    def __init__(self, products_by_sku: dict[str, object]):
        self.products_by_sku = products_by_sku

    def get_by_sku(self, sku: str):
        return self.products_by_sku.get(sku)


def make_row(
    raw_article: str, raw_quantity, row_index: int = 1, sheet_name: str = "test"
):
    return SimpleNamespace(
        row_index=row_index,
        raw_article=raw_article,
        raw_quantity=raw_quantity,
        sheet_name=sheet_name,
    )


def make_product(product_id: int, sku: str, brand: str):
    return SimpleNamespace(
        id=product_id,
        sku=sku,
        brand=brand,
        name=f"Product {sku}",
    )


@pytest.fixture
def matcher():
    m = StockMatcher(session=None)
    return m


def test_matcher_fallback_compact_dot_variant_to_plain_sku(matcher):
    # F404.4 -> F4044
    matcher.product_repo = DummyProductRepo(
        {
            "F4044": make_product(1, "F4044", "FRAP"),
        }
    )

    row = make_row("F404.4", "", row_index=10)
    result = matcher._match_single_row(row)

    assert result.match_status == "matched"
    assert result.product_id == 1
    assert result.brand_derived == "FRAP"
    assert any("fallback SKU variant" in note for note in result.notes)


def test_matcher_fallback_dot_to_dash_variant(matcher):
    # G1107.6 -> G1107-6
    matcher.product_repo = DummyProductRepo(
        {
            "G1107-6": make_product(2, "G1107-6", "GAPPO"),
        }
    )

    row = make_row("G1107.6", "", row_index=20)
    result = matcher._match_single_row(row)

    assert result.match_status == "matched"
    assert result.product_id == 2
    assert result.brand_derived == "GAPPO"
    assert any("G1107-6" in note for note in result.notes)


def test_matcher_fallback_insert_dash_before_last_digit(matcher):
    # F823 -> F82-3
    matcher.product_repo = DummyProductRepo(
        {
            "F82-3": make_product(3, "F82-3", "FRAP"),
        }
    )

    row = make_row("F823", 5, row_index=30)
    result = matcher._match_single_row(row)

    assert result.match_status == "matched"
    assert result.product_id == 3
    assert result.brand_derived == "FRAP"
    assert any("F82-3" in note for note in result.notes)
