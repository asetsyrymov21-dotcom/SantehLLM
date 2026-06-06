from aiogram import Router, types, F
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext

from app.bot.states import UserFlow
from app.bot.keyboards import (
    MAIN_MENU_BUTTON,
    main_menu_keyboard,
)
from app.bot.storage import UserData

router = Router()


@router.message(Command("start"))
async def cmd_start(message: types.Message, state: FSMContext):
    await state.clear()
    await UserData.set_catalog(state, None)
    await state.set_state(UserFlow.main_menu)

    await message.answer(
        "👋 Добро пожаловать в Santeh Catalog!\n\n"
        "💬 <b>Спросить ассистента</b> — спросить про товар или остаток\n"
        "🔎 <b>Поиск товара</b> — найти по SKU или названию\n"
        "📋 <b>Проверить заявку</b> — проверить список SKU или Excel-файл\n"
        "📥 <b>Загрузить остатки</b> — обновить наличие товаров\n\n"
        "Выберите действие:",
        reply_markup=main_menu_keyboard(),
        parse_mode="HTML",
    )


@router.message(Command("menu", "menyu"))
async def cmd_menu(message: types.Message, state: FSMContext):
    await state.clear()
    await state.set_state(UserFlow.main_menu)
    await message.answer("Главное меню:", reply_markup=main_menu_keyboard())


@router.message(F.text == MAIN_MENU_BUTTON)
async def go_main_menu(message: types.Message, state: FSMContext):
    await state.set_state(UserFlow.main_menu)
    await message.answer("Главное меню:", reply_markup=main_menu_keyboard())
