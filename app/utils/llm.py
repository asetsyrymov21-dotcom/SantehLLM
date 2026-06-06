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
) -> str:
    client = _get_client()
    messages = [
        {
            "role": "system",
            "content": (
                "Ты ассистент менеджера магазина сантехники. "
                "Отвечай по-русски, коротко и практично. "
                "Используй только предоставленный контекст и найденные товары. "
                "Не придумывай остатки, цены, сроки поставки, скидки или наличие. "
                "Если вопрос про остатки или цены, скажи, что это проверяется только "
                "по базе через точный SKU. "
                "Не используй Markdown или HTML, отвечай обычным текстом."
            ),
        },
        {
            "role": "user",
            "content": (
                f"INTENT: {intent}\n"
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
