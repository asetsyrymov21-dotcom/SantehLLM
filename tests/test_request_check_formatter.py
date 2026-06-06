from app.services.request_check.formatter import format_checked_lines_for_chat
from app.services.request_check.schemas import CheckedLine


def test_request_check_chat_format_is_manager_friendly():
    text = format_checked_lines_for_chat(
        [
            CheckedLine(
                input_sku="G1017",
                requested_qty=5,
                found=True,
                sku="G1017",
                name="белый смес. д/раковины",
                brand="GAPPO",
                stock_qty=10,
                status="Хватает",
            )
        ]
    )

    assert "✅ <b>G1017</b> — Хватает" in text
    assert "G1017 (белый смес. д/раковины) | GAPPO" in text
    assert "Запрошено: 5 | Остаток: 10" in text
    assert "📊 <b>Итого позиций: 1</b>" in text
    assert "✅ Хватает: 1" in text
    assert "⚠️ Недостаточно: 0" in text
    assert "❌ Нет в наличии: 0" in text
    assert "🔍 Не найдено: 0" in text


def test_request_check_chat_format_handles_not_found():
    text = format_checked_lines_for_chat(
        [
            CheckedLine(
                input_sku="ABC001",
                requested_qty=2,
                found=False,
                stock_qty=0,
                status="Не найден",
            )
        ]
    )

    assert "🔍 <b>ABC001</b> — Не найден" in text
    assert "Не найдено в каталоге" in text
    assert "Запрошено: 2 | Остаток: 0" in text
    assert "🔍 Не найдено: 1" in text
