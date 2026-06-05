from __future__ import annotations

import io

from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile

from app.bot.states import BatchSKUStates
from app.bot.api_client import APIClient
from app.bot.keyboards import CHECK_REQUEST_BUTTON
from app.bot.handlers.menu_actions import (
    CHECK_REQUEST_INSTRUCTION,
    handle_menu_action,
)
from app.services.request_check.excel_parser import parse_excel_request
from app.services.request_check.parser import parse_batch_sku_text
from app.services.request_check.checker import check_request_lines
from app.services.request_check.formatter import (
    calc_summary,
    format_checked_lines_for_chat,
    format_summary,
)
from app.services.request_check.excel_report import (
    generate_excel_report,
    get_report_filename,
)

router = Router()


@router.message(F.text == CHECK_REQUEST_BUTTON)
async def enter_batch_mode_reply(message: types.Message, state: FSMContext):
    await state.set_state(BatchSKUStates.awaiting_input)
    await message.answer(CHECK_REQUEST_INSTRUCTION, parse_mode="HTML")


@router.callback_query(F.data == "batch:check_request")
async def enter_batch_mode(callback: types.CallbackQuery, state: FSMContext):
    await state.set_state(BatchSKUStates.awaiting_input)
    await callback.message.answer(CHECK_REQUEST_INSTRUCTION, parse_mode="HTML")
    await callback.answer()


@router.message(BatchSKUStates.awaiting_input, F.document)
async def handle_batch_excel_file(message: types.Message, state: FSMContext):
    doc = message.document
    filename = doc.file_name or ""

    if not filename.lower().endswith(".xlsx"):
        await message.answer("❌ Нужен файл формата <b>.xlsx</b>", parse_mode="HTML")
        return

    await message.answer("⏳ Читаю файл...")

    file_io = io.BytesIO()
    await message.bot.download(doc, destination=file_io)
    request_lines = parse_excel_request(file_io.getvalue())

    if not request_lines:
        await message.answer(
            "❌ Не удалось найти SKU в файле.\n\n"
            "Убедитесь что первая строка содержит заголовки:\n"
            "<code>SKU, Qty</code> (или артикул, количество)",
            parse_mode="HTML",
        )
        return

    await message.answer(f"⏳ Проверяю {len(request_lines)} позиций...")

    api = APIClient()
    try:
        checked = await check_request_lines(api, request_lines)
    except Exception as e:
        await message.answer(f"❌ Ошибка при проверке: {e}")
        return
    finally:
        await api.close()

    summary = calc_summary(checked)
    summary_text = format_summary(summary)

    if len(checked) <= 10:
        text_result = format_checked_lines_for_chat(checked)
        await message.answer(
            f"{text_result}\n\n{summary_text}", parse_mode="HTML"
        )
    else:
        buf = generate_excel_report(checked)
        filename = get_report_filename()
        await message.answer_document(
            BufferedInputFile(buf.read(), filename=filename),
            caption=f"📊 Проверено {len(checked)} позиций\n\n{summary_text}",
            parse_mode="HTML",
        )

    await state.set_state(BatchSKUStates.awaiting_input)


@router.message(BatchSKUStates.awaiting_input, F.text)
async def handle_batch_input(message: types.Message, state: FSMContext):
    text = message.text.strip()

    if await handle_menu_action(message, state):
        return

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

    await state.set_state(BatchSKUStates.awaiting_input)
