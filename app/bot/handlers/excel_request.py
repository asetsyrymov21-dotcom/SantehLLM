from __future__ import annotations

import io

from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile

from app.bot.states import BatchSKUStates, UserFlow
from app.bot.api_client import APIClient
from app.services.request_check.excel_parser import parse_excel_request
from app.services.request_check.checker import check_request_lines
from app.services.request_check.formatter import (
    format_checked_lines_for_chat,
    format_summary,
    calc_summary,
)
from app.services.request_check.excel_report import (
    generate_excel_report,
    get_report_filename,
)

router = Router()

_INSTRUCTION = (
    "📂 <b>Загрузка Excel-заявки</b>\n\n"
    "Отправьте файл <b>.xlsx</b> с колонками:\n"
    "• <b>SKU</b> (или: артикул, код)\n"
    "• <b>Qty</b> (или: количество, кол-во) — необязательно\n\n"
    "Первая строка — заголовки."
)


@router.message(F.text == "📂 Загрузить Excel-заявку")
async def enter_excel_mode(message: types.Message, state: FSMContext):
    await state.set_state(BatchSKUStates.awaiting_excel_file)
    await message.answer(_INSTRUCTION, parse_mode="HTML")


@router.message(BatchSKUStates.awaiting_excel_file, F.document)
async def handle_excel_file(message: types.Message, state: FSMContext):
    doc = message.document

    if not doc.file_name.endswith(".xlsx"):
        await message.answer("❌ Нужен файл формата <b>.xlsx</b>", parse_mode="HTML")
        return

    await message.answer("⏳ Читаю файл...")

    # скачиваем файл
    file_io = io.BytesIO()
    await message.bot.download(doc, destination=file_io)
    file_bytes = file_io.getvalue()

    request_lines = parse_excel_request(file_bytes)

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
        await api.close()
        await message.answer(f"❌ Ошибка при проверке: {e}")
        return
    await api.close()

    summary = calc_summary(checked)
    summary_text = format_summary(summary)

    if len(checked) <= 10:
        text_result = format_checked_lines_for_chat(checked)
        await message.answer(text_result, parse_mode="HTML")
    else:
        buf = generate_excel_report(checked)
        filename = get_report_filename()
        await message.answer_document(
            BufferedInputFile(buf.read(), filename=filename),
            caption=f"📊 Проверено {len(checked)} позиций\n\n{summary_text}",
            parse_mode="HTML",
        )

    await state.set_state(BatchSKUStates.awaiting_excel_file)


@router.message(BatchSKUStates.awaiting_excel_file, F.text)
async def excel_mode_text_fallback(message: types.Message, state: FSMContext):
    if message.text in (
        "🏠 Главное меню",
        "🔎 Поиск товара",
        "📋 Проверить заявку",
        "📂 Загрузить Excel-заявку",
    ):
        await state.clear()
        await state.set_state(UserFlow.main_menu)
        return
    await message.answer(
        "📎 Пожалуйста, отправьте файл <b>.xlsx</b>", parse_mode="HTML"
    )
