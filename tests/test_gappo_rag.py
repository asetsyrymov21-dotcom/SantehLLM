from scripts.import_gappo_rag import validate_dataset
from app.repositories.rag_repository import _extract_article
from app.services.gappo_catalog import format_gappo_card, search_gappo_cards
from app.utils.llm import generate_assistant_draft_answer


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


def test_extract_article_from_manager_question():
    assert _extract_article("покажи карточку G2406-43") == "G2406-43"


def test_search_gappo_cards_finds_black_kitchen_mixers():
    cards = search_gappo_cards("Какие кухонные смесители есть в черном цвете?", limit=5)

    assert cards
    assert all("Смеситель" in card["name"] for card in cards)
    assert all("кух" in card["name"].lower() for card in cards)
    assert all("чер" in card["color"].lower() for card in cards)


def test_assistant_prompt_allows_rag_cards_when_product_search_is_empty():
    constants = generate_assistant_draft_answer.__code__.co_consts
    prompt_text = "\n".join(str(value) for value in constants if isinstance(value, str))

    assert "PRODUCT SEARCH RESULTS пустой, но в RAG CONTEXT есть точные" in prompt_text
    assert "считай эти карточки найденными товарами компании" in prompt_text
