# handlers/transactions/keyboards.py
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def quick_date_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="📅 Сегодня", callback_data="date_today"),
                InlineKeyboardButton(text="📅 Вчера", callback_data="date_yesterday"),
            ],
            [InlineKeyboardButton(text="🔙 Назад", callback_data="back")],
        ]
    )


def build_category_keyboard(categories, prefix: str):
    buttons = [
        [InlineKeyboardButton(text=c, callback_data=f"{prefix}{c}")]
        for c in categories
    ]
    buttons.append([InlineKeyboardButton(text="➕ Другое", callback_data=f"{prefix}Другое")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def ml_top_keyboard(top, max_buttons: int = 3):
    buttons = []
    for name, p in (top or [])[:max_buttons]:
        percent = p * 100.0
        buttons.append([
            InlineKeyboardButton(
                text=f"{name} ({percent:.1f}%)",
                callback_data=f"ml_pick|{name}",
            )
        ])
    buttons.append([InlineKeyboardButton(text="🔄 Другая", callback_data="ml_other")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)
