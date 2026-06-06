from __future__ import annotations

from aiogram import F, Router, types
from aiogram.fsm.context import FSMContext

from app.bot.api_client import APIClient
from app.bot.handlers.menu_actions import handle_menu_action
from app.bot.keyboards import (
    ASK_ASSISTANT_BUTTON,
    assistant_input_keyboard,
    products_inline_keyboard,
)
from app.bot.states import AssistantStates
from app.services.assistant import AssistantIntent, parse_assistant_question
from app.services.request_check.formatter import format_checked_lines_for_chat
from app.services.request_check.schemas import CheckedLine
from app.utils.sku_utils import normalize_sku

router = Router()

ASSISTANT_INSTRUCTION = (
    "💬 <b>Ассистент</b>\n\n"
    "Спросите обычным текстом, например:\n"
    "<code>Есть G1017 5 шт?</code>\n"
    "<code>Найди белый смеситель для раковины</code>\n\n"
    "По остаткам я отвечаю только по данным из базы."
)


@router.message(F.text == ASK_ASSISTANT_BUTTON)
async def enter_assistant_mode(message: types.Message, state: FSMContext):
    await state.set_state(AssistantStates.awaiting_question)
    await message.answer(
        ASSISTANT_INSTRUCTION,
        reply_markup=assistant_input_keyboard(),
        parse_mode="HTML",
    )


@router.message(AssistantStates.awaiting_question, F.text)
async def handle_assistant_question(message: types.Message, state: FSMContext):
    if await handle_menu_action(message, state):
        return

    question = parse_assistant_question(message.text or "")
    if not question.text:
        await message.answer(
            "Напишите вопрос текстом. Например: <code>Есть G1017 5 шт?</code>",
            reply_markup=assistant_input_keyboard(),
            parse_mode="HTML",
        )
        return

    api = APIClient()
    try:
        if question.intent == AssistantIntent.STOCK_CHECK:
            if not question.sku:
                await message.answer(
                    "Напишите артикул, чтобы я проверил остаток. "
                    "Например: <code>G1017 5 шт</code>.",
                    reply_markup=assistant_input_keyboard(),
                    parse_mode="HTML",
                )
                return
            answer = await _answer_stock_question(
                api, question.sku, question.requested_qty
            )
            await message.answer(
                answer,
                reply_markup=assistant_input_keyboard(),
                parse_mode="HTML",
            )
            return

        if question.intent == AssistantIntent.HELP_QUESTION:
            await message.answer(
                _answer_help_question(question.text),
                reply_markup=assistant_input_keyboard(),
                parse_mode="HTML",
            )
            return

        products = await api.search_products(question.text)
    except Exception as exc:
        await message.answer(
            f"❌ Ошибка ассистента: {exc}",
            reply_markup=assistant_input_keyboard(),
        )
        return
    finally:
        await api.close()

    if not products:
        if question.intent == AssistantIntent.ADVISORY_QUESTION:
            await message.answer(
                _advisory_no_results_answer(),
                reply_markup=assistant_input_keyboard(),
                parse_mode="HTML",
            )
        else:
            await message.answer(
                "Я не нашёл точный артикул или подходящий товар.\n\n"
                "Попробуйте написать артикул, например: <code>G1017 5 шт</code>.",
                reply_markup=assistant_input_keyboard(),
                parse_mode="HTML",
            )
        return

    if question.intent == AssistantIntent.ADVISORY_QUESTION:
        await message.answer(
            "Пока я не собираю комплект автоматически, но нашёл товары, "
            "которые могут подойти. Выберите позицию, и я покажу карточку.",
            reply_markup=assistant_input_keyboard(),
        )

    await _send_product_options(message, products)


async def _answer_stock_question(api: APIClient, sku: str, requested_qty: int) -> str:
    products = await api.search_products(sku)
    product = _find_exact_sku(products, sku)

    if not product:
        line = CheckedLine(
            input_sku=sku,
            requested_qty=requested_qty,
            found=False,
            stock_qty=0,
            status="Не найден",
        )
        return format_checked_lines_for_chat([line])

    inventory = await api.get_inventory(product["id"])
    stock_qty = _stock_qty_from_inventory(inventory)
    status = _resolve_stock_status(stock_qty=stock_qty, requested_qty=requested_qty)

    line = CheckedLine(
        input_sku=sku,
        requested_qty=requested_qty,
        found=True,
        sku=product.get("sku"),
        name=product.get("name"),
        brand=product.get("brand"),
        stock_qty=stock_qty,
        status=status,
    )
    return format_checked_lines_for_chat([line])


def _find_exact_sku(products: list[dict] | None, sku: str) -> dict | None:
    expected = normalize_sku(sku)
    for product in products or []:
        product_sku = normalize_sku(product.get("sku"))
        if product_sku == expected:
            return product
    return None


def _stock_qty_from_inventory(inventory: dict | None) -> int:
    if not inventory:
        return 0
    return int(float(inventory.get("stock_doc") or 0))


def _resolve_stock_status(stock_qty: int, requested_qty: int) -> str:
    if stock_qty <= 0:
        return "Нет в наличии"
    if stock_qty >= requested_qty:
        return "Хватает"
    return "Недостаточно"


async def _send_product_options(message: types.Message, products: list[dict]) -> None:
    await message.answer(
        f"Нашёл варианты: <b>{len(products)}</b>\n\nВыберите товар:",
        reply_markup=products_inline_keyboard(products[:10]),
        parse_mode="HTML",
    )


def _answer_help_question(text: str) -> str:
    normalized = (text or "").lower()

    if "остат" in normalized or "склад" in normalized:
        return (
            "📥 <b>Как загрузить остатки</b>\n\n"
            "Откройте <b>Загрузить остатки</b> и отправьте Excel-файл. "
            "В файле должны быть колонки <b>Артикул</b> и <b>Количество</b> "
            "или похожие названия: <b>SKU</b>, <b>Остаток</b>, <b>Qty</b>, <b>Шт.</b>"
        )

    if "каталог" in normalized:
        return (
            "🧾 <b>Каталог</b>\n\n"
            "Загрузку каталога сейчас выполняет администратор. "
            "Менеджеру лучше пользоваться поиском, проверкой заявки и остатками."
        )

    if "неподдерж" in normalized or "бренд" in normalized:
        return (
            "🚫 <b>Неподдерживаемый бренд</b>\n\n"
            "Это SKU, который не относится к текущим правилам импорта остатков. "
            "Сейчас склад обновляется для <b>FRAP</b> и <b>GAPPO</b>."
        )

    if "не найден" in normalized:
        return (
            "🔍 <b>SKU не найден</b>\n\n"
            "Обычно это значит, что артикула нет в каталоге или он записан иначе. "
            "Попробуйте поискать без точек/дефисов или отправьте SKU администратору."
        )

    return (
        "Я умею проверять остатки по SKU, искать товары и помогать с загрузкой "
        "остатков. Для точной проверки напишите, например: <code>G1017 5 шт</code>."
    )


def _advisory_no_results_answer() -> str:
    return (
        "Пока я не нашёл подходящие товары в каталоге.\n\n"
        "Для подбора лучше уточнить: тип товара, диаметр/размер, бренд, цвет "
        "или назначение. Например: <code>труба 25</code> или "
        "<code>белый смеситель для кухни</code>."
    )
