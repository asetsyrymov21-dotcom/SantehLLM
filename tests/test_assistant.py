from app.services.assistant import AssistantIntent, detect_intent, parse_assistant_question


def test_parse_assistant_stock_question_with_qty_after_sku():
    question = parse_assistant_question("Есть G1017 5 шт?")

    assert question.sku == "G1017"
    assert question.requested_qty == 5
    assert question.intent == AssistantIntent.STOCK_CHECK


def test_parse_assistant_stock_question_with_qty_before_sku():
    question = parse_assistant_question("Нужно 5 штук G1017")

    assert question.sku == "G1017"
    assert question.requested_qty == 5
    assert question.intent == AssistantIntent.STOCK_CHECK


def test_parse_assistant_stock_question_defaults_to_one():
    question = parse_assistant_question("Есть G1307.2004?")

    assert question.sku == "G1307.2004"
    assert question.requested_qty == 1
    assert question.intent == AssistantIntent.STOCK_CHECK


def test_parse_assistant_question_without_sku_keeps_text_for_search():
    question = parse_assistant_question("найди белый смеситель для раковины")

    assert question.sku is None
    assert question.requested_qty == 1
    assert question.text == "найди белый смеситель для раковины"
    assert question.intent == AssistantIntent.PRODUCT_SEARCH


def test_detect_help_question():
    intent = detect_intent("как загрузить остатки?")

    assert intent == AssistantIntent.HELP_QUESTION


def test_detect_advisory_question():
    intent = detect_intent("какие детали нужны чтобы собрать комплект труба 25?")

    assert intent == AssistantIntent.ADVISORY_QUESTION


def test_detect_product_search_question():
    intent = detect_intent("покажи белые смесители для кухни")

    assert intent == AssistantIntent.PRODUCT_SEARCH
