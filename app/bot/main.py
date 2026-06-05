from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer
from aiogram.fsm.storage.memory import MemoryStorage

from app.bot.config import BOT_TOKEN, TELEGRAM_API_BASE_URL
from app.bot.handlers import register_handlers

logger = logging.getLogger(__name__)


async def main() -> None:
    logging.basicConfig(level=logging.INFO)

    if TELEGRAM_API_BASE_URL:
        api_server = TelegramAPIServer.from_base(
            TELEGRAM_API_BASE_URL,
            is_local=True,
        )
        bot = Bot(BOT_TOKEN, session=AiohttpSession(api=api_server))
        logger.info("Using local Telegram Bot API: %s", TELEGRAM_API_BASE_URL)
    else:
        bot = Bot(BOT_TOKEN)

    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)

    register_handlers(dp)

    # Сбрасываем вебхук (если вдруг был) и накопившиеся апдейты,
    # чтобы избежать конфликта при перезапуске
    await bot.delete_webhook(drop_pending_updates=True)
    logger.info("Webhook deleted, pending updates dropped. Starting polling...")

    try:
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
