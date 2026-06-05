from __future__ import annotations

import io

import httpx
from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext

from app.bot.states import StockImportStates
from app.bot.api_client import APIClient
from app.bot.keyboards import IMPORT_STOCK_BUTTON
from app.bot.handlers.menu_actions import (
    STOCK_IMPORT_INSTRUCTION,
    handle_menu_action,
)

router = Router()

def _format_report(data: dict) -> str:
    rows = data.get("rows_scanned", 0)
    updated = data.get("updated", 0)
    unchanged = data.get("unchanged", 0)
    no_product = data.get("skipped_no_product", 0)
    bad_brand = data.get("skipped_unsupported_brand", 0)
    bad_sku = data.get("skipped_invalid_sku", 0)
    bad_qty = data.get("skipped_invalid_qty", 0)
    duplicates = data.get("skipped_duplicate", 0)
    zero_qty = data.get("empty_qty_treated_as_zero", 0)
    errors = data.get("errors", 0)

    lines = [
        "✅ <b>Импорт завершён!</b>\n",
        f"📊 Строк в файле:       <b>{rows}</b>",
        f"✅ Обновлено:           <b>{updated}</b>",
        f"➖ Без изменений:       <b>{unchanged}</b>",
    ]

    if no_product:
        lines.append(f"❓ Не найдено в БД:     <b>{no_product}</b>")
    if bad_brand:
        lines.append(f"🚫 Неподдерж. бренд:   <b>{bad_brand}</b>")
    if duplicates:
        lines.append(f"⚠️ Дубликаты (пропущ.): <b>{duplicates}</b>")
    if bad_sku:
        lines.append(f"⚠️ Пустой/неверный SKU: <b>{bad_sku}</b>")
    if bad_qty:
        lines.append(f"⚠️ Неверное кол-во:    <b>{bad_qty}</b>")
    if zero_qty:
        lines.append(f"ℹ️ Пустое кол-во → 0:  <b>{zero_qty}</b>")
    if errors:
        lines.append(f"❌ Ошибок:             <b>{errors}</b>")

    return "\n".join(lines)


@router.message(F.text == IMPORT_STOCK_BUTTON)
async def enter_stock_import_mode(message: types.Message, state: FSMContext):
    await state.set_state(StockImportStates.awaiting_stock_file)
    await message.answer(STOCK_IMPORT_INSTRUCTION, parse_mode="HTML")


@router.message(StockImportStates.awaiting_stock_file, F.document)
async def handle_stock_file(message: types.Message, state: FSMContext):
    doc = message.document

    if not doc.file_name.endswith(".xlsx"):
        await message.answer(
            "❌ Нужен файл формата <b>.xlsx</b>", parse_mode="HTML"
        )
        return

    await message.answer(
        "⏳ Читаю файл, запускаю импорт...\n\n"
        "Если файл большой, это может занять несколько минут."
    )

    # Скачиваем файл в память
    file_io = io.BytesIO()
    await message.bot.download(doc, destination=file_io)
    file_bytes = file_io.getvalue()

    api = APIClient()
    try:
        result = await api.import_stock(file_bytes, doc.file_name)
    except httpx.TimeoutException:
        await message.answer(
            "⏱ Импорт занимает слишком много времени.\n\n"
            "Файл мог быть большим или API всё ещё обрабатывает данные. "
            "Проверьте остатки чуть позже или отправьте файл ещё раз, если отчёт не появится.",
            parse_mode="HTML",
        )
        return
    except Exception as e:
        await message.answer(
            f"❌ Ошибка при импорте:\n<code>{e}</code>", parse_mode="HTML"
        )
        return
    finally:
        await api.close()

    report_text = _format_report(result)
    await message.answer(report_text, parse_mode="HTML")

    # Остаёмся в том же состоянии — можно загрузить ещё один файл
    await state.set_state(StockImportStates.awaiting_stock_file)


@router.message(StockImportStates.awaiting_stock_file, F.text)
async def stock_import_text_fallback(message: types.Message, state: FSMContext):
    if await handle_menu_action(message, state):
        return
    await message.answer(
        "📎 Пожалуйста, отправьте файл <b>.xlsx</b> с остатками",
        parse_mode="HTML",
    )
