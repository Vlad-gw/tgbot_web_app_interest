# utils/keyboards.py

from aiogram.types import (
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
)
from datetime import datetime


def main_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="💰 Показать баланс"),
                KeyboardButton(text="📜 История транзакций"),
            ],
            [KeyboardButton(text="🗑 Удаление транзакций")],
            [
                KeyboardButton(text="📊 Аналитика"),
                KeyboardButton(text="📈 Прогноз расходов"),
            ],
            [
                KeyboardButton(text="🎯 Установить бюджет"),
                KeyboardButton(text="📁 Экспорт в Excel"),
            ],
            [
                KeyboardButton(text="👤 Профиль"),
                KeyboardButton(text="🔑 Войти на сайт"),
            ],
        ],
        resize_keyboard=True,
        input_field_placeholder="Например: +100000 зарплата вчера 21:21  или  -500 бензин сегодня",
    )


def year_keyboard():
    current_year = datetime.now().year
    buttons = [
        [InlineKeyboardButton(text=str(current_year - i), callback_data=f"year_{current_year - i}")]
        for i in range(5)
    ]
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def back_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="🔙 Назад")]],
        resize_keyboard=True,
    )