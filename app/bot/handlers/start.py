from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext

from app.bot.states import UserFlow
from app.bot.keyboards import main_menu_keyboard
from app.bot.storage import UserData

router = Router()


@router.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    await UserData.set_catalog(state, None)
    await state.set_state(UserFlow.main_menu)

    await message.answer(
        "👋 Добро пожаловать в Santeh Catalog!\n\n"
        "🔎 <b>Поиск товара</b> — найти по SKU или названию\n"
        "📋 <b>Проверить заявку</b> — проверить список SKU\n"
        "📂 <b>Загрузить Excel-заявку</b> — загрузить файл с заявкой\n\n"
        "Выберите действие:",
        reply_markup=main_menu_keyboard(),
        parse_mode="HTML",
    )


@router.message(F.text == "🏠 Главное меню")
async def go_main_menu(message: types.Message, state: FSMContext):
    await state.set_state(UserFlow.main_menu)
    await message.answer("Главное меню:", reply_markup=main_menu_keyboard())
