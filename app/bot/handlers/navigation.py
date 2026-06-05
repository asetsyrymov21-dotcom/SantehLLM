from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext

from app.bot.states import UserFlow
from app.bot.keyboards import main_menu_keyboard
from app.bot.handlers.search import start_search

router = Router()

_MENU_BUTTONS = {
    "🏠 Главное меню",
    "🔎 Поиск товара",
    "📋 Проверить заявку",
    "📂 Загрузить Excel-заявку",
    "🧾 Загрузить каталог",
    "📥 Загрузить остатки",
}


@router.message(F.text == "🏠 Главное меню")
async def go_home(message: types.Message, state: FSMContext):
    await state.set_state(UserFlow.main_menu)
    await message.answer(
        "🏠 Главное меню\n\nВыберите действие:", reply_markup=main_menu_keyboard()
    )
