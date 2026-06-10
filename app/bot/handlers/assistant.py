from __future__ import annotations

import asyncio
import html
import logging

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
from app.utils.llm import generate_assistant_draft_answer
from app.utils.sku_utils import normalize_sku

router = Router()
logger = logging.getLogger(__name__)

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
    product_search_answer = None
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
            cached_answer = await _lookup_memory_answer(
                api, question.text, question.intent.value
            )
            if cached_answer:
                await message.answer(
                    cached_answer,
                    reply_markup=assistant_input_keyboard(),
                    parse_mode="HTML",
                )
                return

            answer = await _generate_help_answer(
                api, question.text, question.intent.value
            )
            await _store_memory_draft(api, question.text, question.intent.value, answer)
            await message.answer(
                answer,
                reply_markup=assistant_input_keyboard(),
                parse_mode="HTML",
            )
            return

        if question.intent == AssistantIntent.ADVISORY_QUESTION:
            cached_answer = await _lookup_memory_answer(
                api, question.text, question.intent.value
            )
            if cached_answer:
                await message.answer(
                    cached_answer,
                    reply_markup=assistant_input_keyboard(),
                    parse_mode="HTML",
                )
                return

        products = await api.search_products(question.text)
        advisory_answer = None
        if question.intent == AssistantIntent.ADVISORY_QUESTION:
            generated_answer = await _generate_advisory_answer(
                api, question.text, question.intent.value, products
            )
            if products:
                advisory_answer = generated_answer or _advisory_with_results_answer()
                await _store_memory_draft(
                    api,
                    question.text,
                    question.intent.value,
                    advisory_answer,
                    source_product_ids=[
                        int(p["id"]) for p in products[:10] if p.get("id")
                    ],
                    meta_json={"source": "llm"} if generated_answer else None,
                )
            else:
                advisory_answer = generated_answer or _advisory_no_results_answer()
                await _store_memory_draft(
                    api,
                    question.text,
                    question.intent.value,
                    advisory_answer,
                    meta_json={"reason": "no_product_candidates"},
                )
        elif question.intent == AssistantIntent.PRODUCT_SEARCH and not products:
            product_search_answer = await _generate_advisory_answer(
                api, question.text, question.intent.value, []
            )
        elif question.intent == AssistantIntent.PRODUCT_SEARCH and products:
            product_search_answer = await _generate_advisory_answer(
                api, question.text, question.intent.value, products
            )
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
                advisory_answer or _advisory_no_results_answer(),
                reply_markup=assistant_input_keyboard(),
                parse_mode="HTML",
            )
        else:
            await message.answer(
                product_search_answer or _product_search_no_results_answer(),
                reply_markup=assistant_input_keyboard(),
                parse_mode="HTML",
            )
        return

    if question.intent == AssistantIntent.ADVISORY_QUESTION:
        await message.answer(
            advisory_answer
            or _advisory_with_results_answer(),
            reply_markup=assistant_input_keyboard(),
        )
    elif question.intent == AssistantIntent.PRODUCT_SEARCH and product_search_answer:
        await message.answer(
            product_search_answer,
            reply_markup=assistant_input_keyboard(),
            parse_mode="HTML",
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


def _advisory_with_results_answer() -> str:
    return (
        "Пока я не собираю комплект автоматически, но нашёл товары, "
        "которые могут подойти. Выберите позицию, и я покажу карточку."
    )


def _advisory_no_results_answer() -> str:
    return (
        "Пока я не нашёл подходящие товары в каталоге.\n\n"
        "Для подбора лучше уточнить: тип товара, диаметр/размер, бренд, цвет "
        "или назначение. Например: <code>труба 25</code> или "
        "<code>белый смеситель для кухни</code>."
    )


def _product_search_no_results_answer() -> str:
    return (
        "Я не нашёл подходящий товар в каталоге.\n\n"
        "Если это народное название, напишите как клиент сказал и добавьте, "
        "для чего нужна деталь. Например: <code>что такое американка для трубы</code> "
        "или <code>нужен уголок мама-папа 20</code>."
    )


async def _generate_help_answer(api: APIClient, question: str, intent: str) -> str:
    generated = await _generate_llm_draft(
        question=question,
        intent=intent,
        help_context=_assistant_help_context(),
        rag_context=await _lookup_rag_context(api, question),
    )
    return generated or _answer_help_question(question)


async def _generate_advisory_answer(
    api: APIClient,
    question: str,
    intent: str,
    products: list[dict] | None,
) -> str | None:
    product_context = _format_product_context(products or [])
    return await _generate_llm_draft(
        question=question,
        intent=intent,
        help_context=_assistant_help_context(),
        rag_context=await _lookup_rag_context(api, question),
        product_context=product_context,
        catalog_bound=bool(product_context)
        or intent == AssistantIntent.PRODUCT_SEARCH.value
        or _is_catalog_bound_question(question),
    )


async def _generate_llm_draft(
    *,
    question: str,
    intent: str,
    help_context: str = "",
    rag_context: str = "",
    product_context: str = "",
    catalog_bound: bool = False,
) -> str | None:
    try:
        answer = await asyncio.to_thread(
            generate_assistant_draft_answer,
            question=question,
            intent=intent,
            help_context=help_context,
            rag_context=rag_context,
            product_context=product_context,
            catalog_bound=catalog_bound,
        )
    except Exception:
        logger.exception("Assistant LLM draft fallback used")
        return None

    clean_answer = (answer or "").strip()
    if not clean_answer:
        return None
    return html.escape(clean_answer)


def _assistant_help_context() -> str:
    return "\n".join(
        [
            "Остатки: менеджер открывает 'Загрузить остатки' и отправляет Excel-файл.",
            "Для импорта остатков нужны колонки с артикулом и количеством: Артикул, SKU, Количество, Остаток, Qty или Шт.",
            "Сейчас склад обновляется для брендов FRAP и GAPPO.",
            "Если SKU не найден, обычно артикула нет в каталоге или он записан иначе; стоит попробовать без точек/дефисов или передать SKU администратору.",
            "Каталог загружает администратор; менеджеру доступны поиск, проверка заявки и остатки.",
            "Остатки и цены нельзя придумывать: они проверяются только по базе и точному SKU.",
            "Если вопрос связан с товарами компании, брендом, каталогом или подбором конкретной позиции, ассистент должен опираться на найденные товары каталога и не заменять их внешними товарами из общих знаний.",
            "Если найденные товары есть, сначала объяснить менеджеру, что похоже подходит, затем задать уточняющие вопросы и предложить выбрать товар из вариантов ниже.",
            "Если вопрос общий технический и не просит товары компании, можно отвечать общими знаниями без привязки к каталогу.",
            "Смесительный узел в сантехнике и отоплении - это группа оборудования, которая смешивает горячую подачу с обраткой, чтобы получить нужную температуру теплоносителя. Часто нужен для теплого пола, потому что теплому полу обычно нужна температура ниже, чем радиаторам.",
            "В смесительный узел обычно входят насос, смесительный клапан, термоголовка или термостатический элемент, коллекторные подключения, краны, воздухоотводчик и иногда байпас. Точный состав зависит от схемы.",
            "Если клиент спрашивает про смесительный узел, уточнить: для теплого пола или радиаторов, площадь/метраж, количество контуров, диаметр трубы, есть ли коллектор и какая температура подачи.",
        ]
    )


def _format_product_context(products: list[dict]) -> str:
    if not products:
        return ""

    lines: list[str] = []
    for index, product in enumerate(products[:10], start=1):
        parts = [
            f"{index}. id={product.get('id')}",
            f"sku={product.get('sku') or 'N/A'}",
            f"name={product.get('name') or 'N/A'}",
            f"brand={product.get('brand') or 'N/A'}",
        ]
        lines.append("; ".join(parts))
    return "\n".join(lines)


def _is_catalog_bound_question(question: str) -> bool:
    normalized = (question or "").lower()
    markers = {
        "наш",
        "у нас",
        "товар",
        "товары",
        "каталог",
        "бренд",
        "бренда",
        "компани",
        "gappo",
        "гаппо",
        "frap",
        "фрап",
    }
    return any(marker in normalized for marker in markers)


async def _lookup_rag_context(api: APIClient, question: str) -> str:
    try:
        result = await api.query_rag(question, limit=3)
    except Exception:
        return ""

    hits = result.get("hits") or []
    blocks: list[str] = []
    for hit in hits[:3]:
        title = hit.get("document_title") or "N/A"
        metadata = hit.get("metadata") or {}
        text = (hit.get("text") or "").strip()
        if not text:
            continue
        article = metadata.get("article")
        source_page = metadata.get("source_page")
        confidence = metadata.get("confidence")
        header_parts = [f"[{title}]"]
        if article:
            header_parts.append(f"[article={article}]")
        if source_page:
            header_parts.append(f"[pdf_page={source_page}]")
        if confidence:
            header_parts.append(f"[confidence={confidence}]")
        blocks.append("\n".join(header_parts) + f"\n{text[:1600]}")
    return "\n---\n".join(blocks)


async def _lookup_memory_answer(
    api: APIClient,
    question: str,
    intent: str,
) -> str | None:
    try:
        result = await api.lookup_assistant_memory(question=question, intent=intent)
    except Exception:
        return None

    if not result.get("found"):
        return None

    entry = result.get("entry") or {}
    return entry.get("answer_text") or None


async def _store_memory_draft(
    api: APIClient,
    question: str,
    intent: str,
    answer_text: str,
    source_product_ids: list[int] | None = None,
    meta_json: dict | None = None,
) -> None:
    try:
        await api.store_assistant_memory(
            question=question,
            intent=intent,
            answer_text=answer_text,
            source_product_ids=source_product_ids or [],
            status="draft",
            meta_json=meta_json,
        )
    except Exception:
        return
