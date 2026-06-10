from __future__ import annotations

import logging

from openai import OpenAI

from app.core.config import settings

logger = logging.getLogger(__name__)


def _get_client() -> OpenAI:
    api_key = settings.openai_api_key
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set")
    return OpenAI(api_key=api_key)


def generate_rag_answer(query: str, context: str) -> str:
    client = _get_client()
    messages = [
        {
            "role": "system",
            "content": (
                "Ты отвечаешь только по предоставленному контексту. "
                "Если в контексте нет ответа — скажи, что ответ не найден в документах. "
                "Не придумывай факты. Отвечай кратко."
            ),
        },
        {
            "role": "user",
            "content": f"QUESTION: {query}\n\nCONTEXT:\n{context}",
        },
    ]
    try:
        resp = client.chat.completions.create(
            model=settings.openai_chat_model,
            messages=messages,
            temperature=0.1,
            max_tokens=400,
        )
        return resp.choices[0].message.content.strip()
    except Exception:
        logger.exception("OpenAI chat completion failed")
        raise


def generate_assistant_draft_answer(
    *,
    question: str,
    intent: str,
    help_context: str = "",
    rag_context: str = "",
    product_context: str = "",
    catalog_bound: bool = False,
) -> str:
    client = _get_client()
    messages = [
        {
            "role": "system",
            "content": (
                "Ты ассистент менеджера магазина сантехники. "
                "Отвечай по-русски как опытный продавец-консультант: понятно, "
                "практично, без сухих канцелярских фраз. "
                "Если вопрос про товары компании, бренд, каталог, подбор конкретной "
                "позиции или найденные товары, отвечай только по PRODUCT SEARCH RESULTS "
                "и RAG CONTEXT. Не подставляй товары, бренды, модели или характеристики "
                "из общих знаний. "
                "Если в RAG CONTEXT есть точная карточка GAPPO с article, используй "
                "её поля как источник характеристик товара; не восстанавливай "
                "характеристики по памяти и не смешивай разные article. "
                "Если confidence=medium или в карточке есть предупреждения, обязательно "
                "сформулируй осторожно: данные требуют проверки по странице PDF. "
                "Если CATALOG_BOUND=yes, считай вопрос привязанным к товарам компании "
                "и не используй общие знания для рекомендаций конкретных товаров. "
                "Если PRODUCT SEARCH RESULTS пустой, не рекомендуй внешние товары; "
                "скажи, что в найденном каталожном контексте подходящих позиций нет, "
                "и задай уточняющие вопросы для поиска. "
                "Общие технические знания можно использовать только для справочных "
                "вопросов без привязки к товарам компании, например про обычные "
                "диаметры труб для отопления дома. "
                "Не придумывай остатки, цены, сроки поставки, скидки или наличие. "
                "Если вопрос про остатки или цены, скажи, что это проверяется только "
                "по базе через точный SKU. "
                "В конце задай 1-3 коротких уточняющих вопроса, если они помогут "
                "подобрать товар компании. Если есть найденные товары, предложи "
                "менеджеру выбрать один из вариантов ниже. "
                "Не используй Markdown или HTML, отвечай обычным текстом."
            ),
        },
        {
            "role": "user",
            "content": (
                f"INTENT: {intent}\n"
                f"CATALOG_BOUND: {'yes' if catalog_bound else 'no'}\n"
                f"QUESTION: {question}\n\n"
                f"HELP CONTEXT:\n{help_context or 'N/A'}\n\n"
                f"RAG CONTEXT:\n{rag_context or 'N/A'}\n\n"
                f"PRODUCT SEARCH RESULTS:\n{product_context or 'N/A'}"
            ),
        },
    ]
    try:
        resp = client.chat.completions.create(
            model=settings.openai_chat_model,
            messages=messages,
            temperature=0.2,
            max_tokens=350,
        )
        return (resp.choices[0].message.content or "").strip()
    except Exception:
        logger.exception("OpenAI assistant draft generation failed")
        raise
