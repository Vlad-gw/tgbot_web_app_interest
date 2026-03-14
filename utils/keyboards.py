# utils/keyboards.py

import os
from datetime import datetime

from aiogram.types import (
    ReplyKeyboardMarkup,
    KeyboardButton,
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    WebAppInfo,
)


def _get_mini_app_url() -> str:
    base_url = os.getenv("MINI_APP_URL", "").strip().rstrip("/")
    if not base_url:
        base_url = os.getenv("SITE_URL", "http://127.0.0.1:8000").strip().rstrip("/")
    return f"{base_url}/miniapp/"


def _is_https_url(url: str) -> bool:
    return url.startswith("https://")


def main_menu():
    keyboard_rows = [
        [
            KeyboardButton(text="💰 Показать баланс"),
            KeyboardButton(text="📜 История транзакций"),
        ],
        [
            KeyboardButton(text="🗑 Удаление транзакций"),
        ],
        [
            KeyboardButton(text="📊 Аналитика"),
            KeyboardButton(text="📈 Прогноз расходов"),
        ],
        [
            KeyboardButton(text="🎯 Установить бюджет"),
            KeyboardButton(text="📁 Экспорт в Excel"),
        ],
        [
            KeyboardButton(text="📥 Импорт выписки"),
        ],
        [
            KeyboardButton(text="👤 Профиль"),
            KeyboardButton(text="🔔 Уведомления"),
        ],
        [
            KeyboardButton(text="📱 Mini App"),
        ],
    ]

    return ReplyKeyboardMarkup(
        keyboard=keyboard_rows,
        resize_keyboard=True,
        input_field_placeholder="Например: +100000 зарплата вчера 21:21  или  -500 бензин сегодня",
    )


def mini_app_inline_keyboard() -> InlineKeyboardMarkup:
    mini_app_url = _get_mini_app_url()

    if _is_https_url(mini_app_url):
        return InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="📱 Открыть Mini App",
                        web_app=WebAppInfo(url=mini_app_url),
                    )
                ]
            ]
        )

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="⚠️ Mini App требует HTTPS",
                    callback_data="miniapp_https_required",
                )
            ]
        ]
    )


def year_keyboard():
    current_year = datetime.now().year

    buttons = [
        [
            InlineKeyboardButton(
                text=str(current_year - i),
                callback_data=f"year_{current_year - i}"
            )
        ]
        for i in range(5)
    ]

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def back_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [
                KeyboardButton(text="🔙 Назад")
            ]
        ],
        resize_keyboard=True,
    )