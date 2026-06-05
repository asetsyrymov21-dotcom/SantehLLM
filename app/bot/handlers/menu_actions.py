from aiogram import types
from aiogram.fsm.context import FSMContext

from app.bot.keyboards import (
    CHECK_EXCEL_REQUEST_BUTTON,
    CHECK_REQUEST_BUTTON,
    IMPORT_CATALOG_BUTTON,
    IMPORT_STOCK_BUTTON,
    LEGACY_CHECK_EXCEL_REQUEST_BUTTON,
    MAIN_MENU_BUTTON,
    SEARCH_PRODUCT_BUTTON,
    main_menu_keyboard,
    search_nav_inline_keyboard,
)
from app.bot.states import BatchSKUStates, StockImportStates, UserFlow


CHECK_REQUEST_INSTRUCTION = (
    "📋 <b>Проверка заявки</b>\n\n"
    "Отправьте заявку одним из способов:\n\n"
    "• файл <b>.xlsx</b> с колонками <b>SKU</b> и <b>Qty</b>\n"
    "• текстом — SKU по одному в строке\n\n"
    "В тексте можно указывать количество:\n\n"
    "<code>G1012\n"
    "G1013 2\n"
    "F2001 x3\n"
    "H5010 *2\n"
    "K3030, 5</code>\n\n"
    "Если количество не указано — считается 1 шт."
)

STOCK_IMPORT_INSTRUCTION = (
    "📥 <b>Загрузка остатков</b>\n\n"
    "Отправьте файл <b>.xlsx</b> с остатками.\n\n"
    "Обязательные колонки:\n"
    "• <b>Артикул</b> (или: арт., sku, код)\n"
    "• <b>Количество</b> (или: остаток, qty, наличие, шт.)\n\n"
    "Поддерживаемые бренды: <b>FRAP</b> и <b>GAPPO</b>.\n"
    "Первая строка — заголовки."
)


async def handle_menu_action(message: types.Message, state: FSMContext) -> bool:
    text = (message.text or "").strip()

    if text == MAIN_MENU_BUTTON:
        await state.clear()
        await state.set_state(UserFlow.main_menu)
        await message.answer("Главное меню:", reply_markup=main_menu_keyboard())
        return True

    if text == SEARCH_PRODUCT_BUTTON:
        await state.set_state(UserFlow.search_input)
        await message.answer(
            "🔎 Введите SKU или название товара.\n"
            "Можно отправлять несколько запросов подряд.",
            reply_markup=search_nav_inline_keyboard(),
        )
        return True

    if text in {
        CHECK_REQUEST_BUTTON,
        CHECK_EXCEL_REQUEST_BUTTON,
        LEGACY_CHECK_EXCEL_REQUEST_BUTTON,
    }:
        await state.set_state(BatchSKUStates.awaiting_input)
        await message.answer(CHECK_REQUEST_INSTRUCTION, parse_mode="HTML")
        return True

    if text == IMPORT_STOCK_BUTTON:
        await state.set_state(StockImportStates.awaiting_stock_file)
        await message.answer(STOCK_IMPORT_INSTRUCTION, parse_mode="HTML")
        return True

    if text == IMPORT_CATALOG_BUTTON:
        await state.clear()
        await state.set_state(UserFlow.main_menu)
        await message.answer(
            "🧾 Загрузку каталога выполняет администратор.\n\n"
            "Актуальное меню:",
            reply_markup=main_menu_keyboard(),
        )
        return True

    return False
