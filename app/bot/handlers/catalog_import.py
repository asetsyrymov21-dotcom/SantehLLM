from __future__ import annotations

import io

from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext

from app.bot.api_client import APIClient
from app.bot.keyboards import (
    IMPORT_CATALOG_BUTTON,
    MAIN_MENU_BUTTONS,
    main_menu_keyboard,
)
from app.bot.states import CatalogImportStates, UserFlow

router = Router()

_INSTRUCTION = (
    "🧾 <b>Загрузка каталога товаров</b>\n\n"
    "Отправьте файл <b>.xlsx</b> с каталогом/прайсом.\n\n"
    "Файл должен содержать колонки с артикулом, названием и ценой.\n"
    "Для текущих прайсов заголовки ожидаются на 3-й строке Excel."
)

def _format_report(data: dict) -> str:
    built = data.get("built_products", 0)
    inserted = data.get("inserted", 0)
    updated = data.get("updated", 0)
    failed = data.get("failed", 0)
    enrichment = data.get("needs_pdf_enrichment", 0)
    fallback = data.get("name_fallback_to_sku", 0)
    empty_title = data.get("title_empty_in_excel", 0)
    weak_title = data.get("weak_title_after_normalize", 0)

    lines = [
        "✅ <b>Каталог импортирован!</b>\n",
        f"📄 Файл: <b>{data.get('filename', '')}</b>",
        f"📊 Товаров обработано: <b>{built}</b>",
        f"🆕 Добавлено: <b>{inserted}</b>",
        f"🔄 Обновлено: <b>{updated}</b>",
    ]

    if failed:
        lines.append(f"❌ Ошибок: <b>{failed}</b>")
    if enrichment:
        lines.append(f"ℹ️ Нужна PDF-доработка: <b>{enrichment}</b>")
    if fallback:
        lines.append(f"⚠️ Название заменено SKU: <b>{fallback}</b>")
    if empty_title:
        lines.append(f"⚠️ Пустое название в Excel: <b>{empty_title}</b>")
    if weak_title:
        lines.append(f"⚠️ Слабое название: <b>{weak_title}</b>")

    return "\n".join(lines)


@router.message(F.text == IMPORT_CATALOG_BUTTON)
async def enter_catalog_import_mode(message: types.Message, state: FSMContext):
    await state.clear()
    await state.set_state(UserFlow.main_menu)
    await message.answer(
        "🧾 Загрузку каталога выполняет администратор.\n\n"
        "Актуальное меню:",
        reply_markup=main_menu_keyboard(),
    )


@router.message(CatalogImportStates.awaiting_catalog_file, F.document)
async def handle_catalog_file(message: types.Message, state: FSMContext):
    doc = message.document
    filename = doc.file_name or ""

    if not filename.lower().endswith(".xlsx"):
        await message.answer("❌ Нужен файл формата <b>.xlsx</b>", parse_mode="HTML")
        return

    await message.answer("⏳ Читаю каталог и обновляю базу...")

    file_io = io.BytesIO()
    await message.bot.download(doc, destination=file_io)
    file_bytes = file_io.getvalue()

    api = APIClient()
    try:
        result = await api.import_catalog_excel(file_bytes, filename)
    except Exception as e:
        await message.answer(
            f"❌ Ошибка при импорте каталога:\n<code>{e}</code>",
            parse_mode="HTML",
        )
        return
    finally:
        await api.close()

    await message.answer(_format_report(result), parse_mode="HTML")
    await state.set_state(CatalogImportStates.awaiting_catalog_file)


@router.message(CatalogImportStates.awaiting_catalog_file, F.text)
async def catalog_import_text_fallback(message: types.Message, state: FSMContext):
    if message.text in MAIN_MENU_BUTTONS:
        await state.clear()
        return
    await message.answer(
        "📎 Пожалуйста, отправьте файл <b>.xlsx</b> с каталогом",
        parse_mode="HTML",
    )
