# utils/budget_keyboards.py
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def categories_inline_keyboard(categories: list[tuple[int, str]]) -> InlineKeyboardMarkup:
    rows = []

    for cid, name in categories:
        rows.append([InlineKeyboardButton(text=name, callback_data=f"budget_cat_{cid}")])

    rows.append([InlineKeyboardButton(text="➕ Другое", callback_data="budget_other")])
    rows.append([InlineKeyboardButton(text="📊 Аналитика бюджета", callback_data="budget_analytics")])
    rows.append([InlineKeyboardButton(text="❌ Отмена", callback_data="budget_cancel")])

    return InlineKeyboardMarkup(inline_keyboard=rows)