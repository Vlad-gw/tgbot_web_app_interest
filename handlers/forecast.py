# handlers/forecast.py
from aiogram import Router, F
from aiogram.types import Message

from services.forecast import build_expense_forecast_message

router = Router()


@router.message(F.text == "📈 Прогноз расходов")
async def forecast_expenses(message: Message):
    await message.answer("📊 Анализируем ваши расходы...")

    telegram_id = message.from_user.id
    text = await build_expense_forecast_message(telegram_id=telegram_id)

    await message.answer(text)