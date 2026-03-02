# Точка входа в бота
import asyncio
import logging
import os
from aiogram import Bot, Dispatcher
from aiogram.enums.parse_mode import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import BotCommand
from dotenv import load_dotenv
from aiogram.client.default import DefaultBotProperties
from handlers import admin

# Импорт календаря и всех хендлеров
from aiogram_calendar import SimpleCalendarCallback
from handlers import start, transactions, delete, balance, history, analytics, export, profile
from database.db import db


# Загрузка .env
load_dotenv()
BOT_TOKEN = os.getenv("BOT_TOKEN")

# Настройка логов
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Инициализация бота и диспетчера
bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)
dp = Dispatcher(storage=MemoryStorage())

# Регистрация всех роутеров (хендлеров)
def register_routers():
    dp.include_router(start.router)
    dp.include_router(transactions.router)
    dp.include_router(delete.router)
    dp.include_router(balance.router)
    dp.include_router(history.router)
    dp.include_router(analytics.router)
    dp.include_router(export.router)
    dp.include_router(profile.router)
    dp.include_router(admin.router)

# Установка команд бота
async def set_bot_commands():
    commands = [
        BotCommand(command="start", description="Начать работу"),
        BotCommand(command="profile", description="Профиль"),
        BotCommand(command="admin", description="Админ-панель"),
    ]
    await bot.set_my_commands(commands)

# Главная точка входа
async def main():
    await db.connect()
    register_routers()
    await set_bot_commands()
    logger.info("Бот запущен!")
    await dp.start_polling(bot)

# Запуск
if __name__ == '__main__':
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Бот остановлен.")

