"""Standalone entrypoint for the aiogram 3.x Telegram Bot process (`bot` service)."""

import asyncio
import logging

from aiogram import Bot, Dispatcher

from app.core.config import settings
from app.core.logging import setup_logging
from app.modules.telegram.handlers.admin import admin_router
from app.modules.telegram.handlers.customer import customer_router

logger = logging.getLogger(__name__)


def create_dispatcher() -> Dispatcher:
    dp = Dispatcher()
    dp.include_router(admin_router)
    dp.include_router(customer_router)
    return dp


async def run_bot() -> None:
    setup_logging(debug=settings.DEBUG)
    bot = Bot(token=settings.TELEGRAM_BOT_TOKEN)
    dp = create_dispatcher()
    logger.info("Starting Telegram Bot polling...")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(run_bot())
