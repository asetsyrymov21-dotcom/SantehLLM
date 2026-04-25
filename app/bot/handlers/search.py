from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext

from app.bot.states import UserFlow
from app.bot.keyboards import (
    main_menu_keyboard,
    products_inline_keyboard,
    search_nav_inline_keyboard,
)
from app.bot.storage import UserData
from app.bot.api_client import APIClient

router = Router()


@router.message(F.text == "🔎 Поиск товара")
async def start_search(message: types.Message, state: FSMContext):
    await state.set_state(UserFlow.search_input)
    await message.answer(
        "🔎 Введите SKU или название товара.\nМожно отправлять несколько запросов подряд.",
        reply_markup=search_nav_inline_keyboard(),
    )


@router.message(UserFlow.search_input, F.text)
async def do_search(message: types.Message, state: FSMContext):
    """Выполнить поиск"""
    query = message.text.strip()

    if query == "🏠 Главное меню":
        return

    if len(query) < 2:
        await message.answer(
            "❌ Введите минимум 2 символа:", reply_markup=search_nav_inline_keyboard()
        )
        return

    await UserData.set_last_query(state, query)

    api = APIClient()
    try:
        products = await api.search_products(query)
    except Exception as exc:
        await api.close()
        await message.answer(
            f"❌ Ошибка поиска: {exc}", reply_markup=search_nav_inline_keyboard()
        )
        return
    await api.close()

    if not products:
        await message.answer(
            "❌ Ничего не найдено\n\nПопробуйте другой запрос:",
            reply_markup=search_nav_inline_keyboard(),
        )
        return

    await state.set_state(UserFlow.search_input)

    await message.answer(
        f"🔎 Найдено: <b>{len(products)}</b>\n\nВыберите товар:",
        reply_markup=products_inline_keyboard(products[:10]),
        parse_mode="HTML",
    )

    @router.callback_query(F.data == "search:exit")
    async def exit_search(callback: types.CallbackQuery, state: FSMContext):
        await state.set_state(UserFlow.main_menu)
        await callback.message.answer(
            "Главное меню:", reply_markup=main_menu_keyboard()
        )
        await callback.answer()

    @router.callback_query(F.data == "search:stay")
    async def stay_in_search(callback: types.CallbackQuery, state: FSMContext):
        await state.set_state(UserFlow.search_input)
        await callback.message.answer(
            "🔎 Введите SKU или название товара.\nМожно отправлять несколько запросов подряд.",
            reply_markup=search_nav_inline_keyboard(),
        )
        await callback.answer()

    @router.callback_query(F.data == "menu:main")
    async def back_to_main_menu(callback: types.CallbackQuery, state: FSMContext):
        await state.set_state(UserFlow.main_menu)
        await callback.message.answer(
            "Главное меню:", reply_markup=main_menu_keyboard()
        )
        await callback.answer()
