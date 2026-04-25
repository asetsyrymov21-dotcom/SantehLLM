from __future__ import annotations

from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile

from app.bot.states import UserFlow, BatchSKUStates
from app.bot.api_client import APIClient
from app.services.request_check.parser import parse_batch_sku_text
from app.services.request_check.checker import check_request_lines
from app.services.request_check.formatter import format_checked_lines_for_chat
from app.services.request_check.excel_report import (
    generate_excel_report,
    get_report_filename,
)

router = Router()

_INSTRUCTION = (
    "📋 <b>Проверка заявки</b>\n\n"
    "Отправьте список SKU — по одному в строке.\n"
    "Можно указывать количество:\n\n"
    "<code>G1012\n"
    "G1013 2\n"
    "F2001 x3\n"
    "H5010 *2\n"
    "K3030, 5</code>\n\n"
    "Если количество не указано — считается 1 шт."
)


@router.callback_query(F.data == "batch:check_request")
async def enter_batch_mode(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(BatchSKUStates.awaiting_input)
    await callback.message.answer(_INSTRUCTION, parse_mode="HTML")
    await callback.answer()


@router.message(BatchSKUStates.awaiting_input, F.text)
async def handle_batch_input(message: types.Message, state: FSMContext):
    text = message.text.strip()

    request_lines = parse_batch_sku_text(text)
    if not request_lines:
        await message.answer(
            "❌ Не удалось распознать ни одного SKU. Попробуйте ещё раз."
        )
        return

    await message.answer(f"⏳ Проверяю {len(request_lines)} позиций...")

    api = APIClient()
    try:
        checked = await check_request_lines(api, request_lines)
    except Exception as e:
        await api.close()
        await message.answer(f"❌ Ошибка при проверке: {e}")
        return
    await api.close()

    # <= 10 строк → текст, > 10 → Excel
    if len(checked) <= 10:
        text_result = format_checked_lines_for_chat(checked)
        await message.answer(text_result, parse_mode="HTML")
    else:
        buf = generate_excel_report(checked)
        filename = get_report_filename()
        await message.answer_document(
            BufferedInputFile(buf.read(), filename=filename),
            caption=f"📊 Проверено {len(checked)} позиций",
        )

    # остаёмся в том же state — пользователь может прислать новый список
    await state.set_state(BatchSKUStates.awaiting_input)
