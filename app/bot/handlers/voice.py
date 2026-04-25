from __future__ import annotations

import time
from io import BytesIO

from aiogram import Router, F, types
from aiogram.fsm.context import FSMContext
from aiogram import Bot

from app.bot.api_client import APIClient
from app.bot.keyboards import products_keyboard
from app.bot.stt.stub import StubSTT

router = Router()
stt_provider = StubSTT()


@router.message(F.voice)
async def handle_voice(message: types.Message, bot: Bot, state: FSMContext):
    # Voice is only for search entry. No sale creation from voice.
    voice = message.voice
    file = await bot.get_file(voice.file_id)
    buf = BytesIO()
    await bot.download_file(file.file_path, buf)
    data = buf.getvalue()
    try:
        text = await stt_provider.recognize(data, mime_type="audio/ogg")
    except Exception as exc:
        await message.answer(f"Не удалось распознать голос: {exc}")
        return

    await message.answer(
        f"Распознал: {text}\n\nНиже результаты поиска. Выберите нужный товар кнопкой."
    )
    api = APIClient()
    try:
        products = await api.search_products(text)
    except Exception as exc:
        await message.answer(f"Ошибка поиска: {exc}")
        await api.close()
        return
    await api.close()
    if not products:
        await message.answer("По вашему запросу ничего не найдено")
        return
    await message.answer("Результаты:", reply_markup=products_keyboard(products))
    # Clear any pending sale FSM state to avoid unintended flows
    await state.clear()
