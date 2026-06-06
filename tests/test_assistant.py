from app.services.assistant import parse_assistant_question


def test_parse_assistant_stock_question_with_qty_after_sku():
    question = parse_assistant_question("Есть G1017 5 шт?")

    assert question.sku == "G1017"
    assert question.requested_qty == 5


def test_parse_assistant_stock_question_with_qty_before_sku():
    question = parse_assistant_question("Нужно 5 штук G1017")

    assert question.sku == "G1017"
    assert question.requested_qty == 5


def test_parse_assistant_stock_question_defaults_to_one():
    question = parse_assistant_question("Есть G1307.2004?")

    assert question.sku == "G1307.2004"
    assert question.requested_qty == 1


def test_parse_assistant_question_without_sku_keeps_text_for_search():
    question = parse_assistant_question("найди белый смеситель для раковины")

    assert question.sku is None
    assert question.requested_qty == 1
    assert question.text == "найди белый смеситель для раковины"
