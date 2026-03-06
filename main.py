# main.py — точка входа в бота

import asyncio
import logging
import os

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums.parse_mode import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand
from dotenv import load_dotenv

from database.db import db

# handlers
from handlers import admin
from handlers import (
    start,
    quick_add,
    transactions,
    delete,
    balance,
    history,
    analytics,
    export,
    profile,
    site_login,
    forecast,
    budget,
    import_statement,
)

# Загружаем .env один раз в точке входа
load_dotenv()

# Настройка логов
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise RuntimeError("❌ BOT_TOKEN не найден в .env")

# Инициализация бота и диспетчера
bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
dp = Dispatcher(storage=MemoryStorage())


def register_routers() -> None:
    # Базовые
    dp.include_router(start.router)

    # Быстрый текстовый ввод +1000 / -500
    dp.include_router(quick_add.router)

    # Транзакции
    dp.include_router(transactions.router)

    # Импорт выписки
    dp.include_router(import_statement.router)

    # Остальные модули
    dp.include_router(delete.router)
    dp.include_router(balance.router)
    dp.include_router(history.router)
    dp.include_router(analytics.router)
    dp.include_router(export.router)
    dp.include_router(profile.router)
    dp.include_router(forecast.router)
    dp.include_router(site_login.router)
    dp.include_router(admin.router)
    dp.include_router(budget.router)


async def set_bot_commands() -> None:
    commands = [
        BotCommand(command="start", description="Начать работу"),
        BotCommand(command="profile", description="Профиль"),
        BotCommand(command="admin", description="Админ-панель"),
    ]
    await bot.set_my_commands(commands)


async def main() -> None:
    await db.connect()
    register_routers()
    await set_bot_commands()

    logger.info("Бот запущен!")
    await dp.start_polling(bot)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Бот остановлен.")