from scripts.import_gappo_rag import validate_dataset
from app.services.gappo_catalog import format_gappo_card


def test_validate_dataset_allows_duplicate_articles_indexed_once():
    chunks = [
        {"metadata": {"article": "G4150"}, "text": "one"},
        {"metadata": {"article": "G4150"}, "text": "two"},
        {"metadata": {"article": "G1052-80"}, "text": "three"},
    ]
    products = [
        {"article": "G4150"},
        {"article": "G4150"},
        {"article": "G1052-80"},
    ]
    indexes = {"by_article": {"G4150": {}, "G1052-80": {}}}

    report = validate_dataset(chunks=chunks, products=products, indexes=indexes)

    assert report["errors"] == []
    assert report["duplicate_product_articles"] == {"G4150": 2}
    assert report["duplicate_chunk_articles"] == {"G4150": 2}


def test_format_gappo_card_warns_for_medium_confidence():
    text = format_gappo_card(
        {
            "article": "G2406-43",
            "name": "Душевая система",
            "category": "Душевые системы",
            "package_size": "675x420x130mm",
            "packing": "1/3PCS",
            "items_per_pack": 1,
            "items_per_carton": 3,
            "source": {"page": 97},
            "quality": {"confidence": "medium", "issues": ["needs manual check"]},
        }
    )

    assert "Точная карточка GAPPO: G2406-43" in text
    assert "Размер упаковки: 675x420x130mm" in text
    assert "Фасовка: 1/3PCS" in text
    assert "Данные требуют проверки по странице PDF: 97." in text
