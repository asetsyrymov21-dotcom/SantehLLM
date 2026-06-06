from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext

from app.bot.states import UserFlow
from app.bot.keyboards import MAIN_MENU_BUTTON, main_menu_keyboard
from app.bot.config import is_admin_user

router = Router()


@router.message(F.text == MAIN_MENU_BUTTON)
async def go_home(message: types.Message, state: FSMContext):
    await state.set_state(UserFlow.main_menu)
    await message.answer(
        "🏠 Главное меню\n\nВыберите действие:",
        reply_markup=main_menu_keyboard(
            is_admin=is_admin_user(message.from_user.id if message.from_user else None)
        ),
    )
