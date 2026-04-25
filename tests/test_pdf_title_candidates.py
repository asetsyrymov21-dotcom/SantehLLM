from app.services.pdf.product_cards import _extract_title_candidates
from app.services.pdf.product_cards import extract_product_cards_from_page
from app.services.pdf.extractor import extract_catalog_grids_from_page


PDF_PATH = "2026 GAPPOсмесители каталог .pdf"


def test_title_candidates_trim_numeric_tail_before_material_label():
    candidates = _extract_title_candidates(
        "G3306-9 Встраиваемый смеситель для ванны и душа 420 "
        "Материал корпуса： латунь Размер упаковки: 535x295x80mm",
        "G3306-9",
    )

    assert "G3306-9 Встраиваемый смеситель для ванны и душа" in candidates


def test_title_candidates_trim_finish_garbage_after_product_name():
    candidates = _extract_title_candidates(
        "G5006-9 Смеситель для биде 35 ору сж тае лй ьная "
        "G51-6 G79-FX2-9 1/8 PCS",
        "G5006-9",
    )

    assert candidates[0] == "G5006-9 Смеситель для биде"


def _titles_by_sku(page: int) -> dict[str, str]:
    blocks = extract_product_cards_from_page(PDF_PATH, page, "GAPPO")
    return {block.rows[0]["sku"]: block.title for block in blocks if block.rows}


def test_layout_listing_extracts_standalone_mixer_items():
    titles = _titles_by_sku(54)

    assert titles["G13102-13"] == (
        "G13102-13 Смеситель для раковины на два отверстия, "
        "устанавливаемый на столешницу"
    )
    assert titles["G12102-13B"] == (
        "G12102-13B Смеситель для раковины встраиваемый с двумя ручками"
    )


def test_layout_listing_extracts_shower_heads_components_and_hoses():
    shower_titles = _titles_by_sku(283)
    component_titles = _titles_by_sku(288)
    hose_titles = _titles_by_sku(291)

    assert shower_titles["G33-3"] == (
        "G33-3 Душевая лейка 1-режим цвет-сатин золотой"
    )
    assert component_titles["G59-20"] == (
        "G59-20 Кран-букса переключающего клапана с тремя функциями "
        "(90°, с запорным клапаном)"
    )
    assert hose_titles["G45-43"] == (
        "G45-43 150cm Шланг в двойной оплетке усиленный "
        "нержавеющая сталь цвет-Матовое розовое золото"
    )


def test_catalog_overview_page_is_ignored():
    assert extract_product_cards_from_page(PDF_PATH, 28, "GAPPO") == []
    assert extract_catalog_grids_from_page(PDF_PATH, 28, "GAPPO") == []
