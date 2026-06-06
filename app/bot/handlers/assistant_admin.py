from __future__ import annotations

import html

from aiogram import F, Router, types
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder

from app.bot.api_client import APIClient
from app.bot.config import is_admin_user
from app.bot.keyboards import ASSISTANT_DRAFTS_BUTTON

router = Router()


@router.message(Command("my_id"))
async def show_my_id(message: types.Message):
    user_id = message.from_user.id if message.from_user else None
    await message.answer(f"Ваш Telegram ID: <code>{user_id}</code>", parse_mode="HTML")


@router.message(Command("assistant_drafts"))
async def show_assistant_drafts(message: types.Message):
    await _show_assistant_drafts(message)


@router.message(F.text == ASSISTANT_DRAFTS_BUTTON)
async def show_assistant_drafts_from_button(message: types.Message):
    await _show_assistant_drafts(message)


async def _show_assistant_drafts(message: types.Message):
    if not is_admin_user(message.from_user.id if message.from_user else None):
        await message.answer("Этот раздел доступен только администратору.")
        return

    await send_first_draft(message)


async def send_first_draft(message: types.Message) -> None:
    await _send_draft(message, offset=0)


@router.callback_query(F.data.startswith("assistant_memory:"))
async def handle_assistant_memory_action(callback: types.CallbackQuery):
    if not is_admin_user(callback.from_user.id if callback.from_user else None):
        await callback.answer("Только для администратора", show_alert=True)
        return

    parts = (callback.data or "").split(":")
    if len(parts) < 3:
        await callback.answer("Некорректное действие", show_alert=True)
        return

    action = parts[1]
    entry_id = int(parts[2])
    offset = int(parts[3]) if len(parts) > 3 and parts[3].isdigit() else 0

    api = APIClient()
    try:
        if action == "approve":
            await api.approve_assistant_memory(entry_id)
            await callback.answer("Утверждено")
        elif action == "delete":
            await api.delete_assistant_memory(entry_id)
            await callback.answer("Удалено")
        elif action == "next":
            await callback.answer()
            await api.close()
            await _send_draft(callback.message, offset=offset + 1)
            return
        else:
            await callback.answer("Неизвестное действие", show_alert=True)
            return
    except Exception as exc:
        await callback.answer("Ошибка", show_alert=True)
        await callback.message.answer(f"❌ Ошибка админки: {html.escape(str(exc))}")
        return
    finally:
        await api.close()

    await _send_draft(callback.message, offset=offset)


async def _send_draft(message: types.Message, offset: int) -> None:
    api = APIClient()
    try:
        result = await api.list_assistant_memory(status="draft", limit=1, offset=offset)
    except Exception as exc:
        await message.answer(f"❌ Ошибка загрузки draft: {html.escape(str(exc))}")
        return
    finally:
        await api.close()

    total = int(result.get("total") or 0)
    entries = result.get("entries") or []

    if not entries:
        if total and offset > 0:
            await _send_draft(message, offset=max(0, total - 1))
            return
        await message.answer("Черновиков ассистента нет.")
        return

    entry = entries[0]
    await message.answer(
        _format_draft(entry=entry, offset=offset, total=total),
        reply_markup=_draft_keyboard(entry_id=int(entry["id"]), offset=offset),
        parse_mode="HTML",
    )


def _format_draft(entry: dict, offset: int, total: int) -> str:
    question = html.escape(entry.get("raw_question_example") or "")
    answer = html.escape(_truncate(entry.get("answer_text") or "", limit=2400))
    intent = html.escape(entry.get("intent") or "")
    hit_count = int(entry.get("hit_count") or 0)

    return (
        f"📝 <b>Черновик {offset + 1}/{total}</b>\n\n"
        f"<b>Вопрос:</b>\n{question}\n\n"
        f"<b>Ответ:</b>\n{answer}\n\n"
        f"<b>Intent:</b> <code>{intent}</code>\n"
        f"<b>Использований:</b> {hit_count}"
    )


def _draft_keyboard(entry_id: int, offset: int):
    kb = InlineKeyboardBuilder()
    kb.button(
        text="✅ Утвердить",
        callback_data=f"assistant_memory:approve:{entry_id}:{offset}",
    )
    kb.button(
        text="🗑 Удалить",
        callback_data=f"assistant_memory:delete:{entry_id}:{offset}",
    )
    kb.button(
        text="➡️ Следующий",
        callback_data=f"assistant_memory:next:{entry_id}:{offset}",
    )
    kb.adjust(2, 1)
    return kb.as_markup()


def _truncate(text: str, limit: int) -> str:
    clean_text = (text or "").strip()
    if len(clean_text) <= limit:
        return clean_text
    return clean_text[: limit - 1].rstrip() + "…"
