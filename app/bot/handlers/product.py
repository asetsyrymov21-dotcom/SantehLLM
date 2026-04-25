from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext

from app.bot.states import UserFlow
from app.bot.keyboards import (
    product_view_keyboard,
    product_actions_inline_keyboard,
    search_input_keyboard,
    search_results_keyboard,
    products_inline_keyboard,
)
from app.bot.storage import UserData
from app.bot.api_client import APIClient

router = Router()


def format_product_card(product: dict, inventory: dict | None) -> str:
    """Форматирование карточки товара"""
    brand = product.get("brand") or "Gappo"
    category = product.get("category") or "-"
    price = product.get("price")
    currency = product.get("currency") or "KZT"
    unit = product.get("unit") or "шт"

    lines = [
        f"📦 <b>{product['name']}</b>",
        f"",
        f"🏷️ SKU: <code>{product.get('sku', '-')}</code>",
        f"🏭 Бренд: {brand}",
        f"📂 Категория: {category}",
    ]

    if price:
        lines.append(f"💰 Цена: {price} {currency}")

    # Проверка: inventory существует И stock_doc не None (0 - валидное значение)
    if inventory is not None and inventory.get("stock_doc") is not None:
        stock = inventory["stock_doc"]
        lines.append(f"📦 Остаток: {stock} {unit}")
    else:
        lines.append(f"📦 Остаток: уточняется")

    return "\n".join(lines)


@router.callback_query(F.data.startswith("prod:"))
async def show_product(call: types.CallbackQuery, state: FSMContext):
    """Показать детали товара"""
    await call.answer()

    product_id = int(call.data.split(":", 1)[1])

    api = APIClient()
    try:
        product = await api.get_product(product_id)
        inventory = await api.get_inventory(product_id)
    except Exception as exc:
        await api.close()
        await call.message.answer(f"❌ Ошибка: {exc}")
        return
    await api.close()

    await state.set_state(UserFlow.product_view)
    await state.update_data(viewed_product_id=product_id)

    text = format_product_card(product, inventory)

    await call.message.answer(
        text,
        reply_markup=product_actions_inline_keyboard(product_id),
        parse_mode="HTML",
    )


@router.message(UserFlow.product_view, F.text == "⬅️ Назад")
async def back_from_product(message: types.Message, state: FSMContext):
    await state.set_state(UserFlow.search_input)
    await message.answer(
        "🔎 Введите SKU или название товара:", reply_markup=search_input_keyboard()
    )


@router.message(UserFlow.product_view, F.text == "🔎 Новый поиск")
async def new_search_from_product(message: types.Message, state: FSMContext):
    """Новый поиск из просмотра товара"""
    await state.set_state(UserFlow.search_input)
    await message.answer(
        "🔎 Введите SKU или название товара:", reply_markup=search_input_keyboard()
    )
