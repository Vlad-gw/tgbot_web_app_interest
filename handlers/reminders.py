# handlers/reminders.py

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from database.db import db
from utils.keyboards import main_menu

router = Router()


def reminders_inline_keyboard(enabled: bool) -> InlineKeyboardMarkup:
    status_text = "✅ Включены" if enabled else "❌ Выключены"

    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text=f"Статус: {status_text}",
                    callback_data="reminder_status_info",
                )
            ],
            [
                InlineKeyboardButton(
                    text="✅ Включить",
                    callback_data="reminder_enable",
                ),
                InlineKeyboardButton(
                    text="❌ Выключить",
                    callback_data="reminder_disable",
                ),
            ],
            [
                InlineKeyboardButton(
                    text="🔙 Назад",
                    callback_data="reminder_back",
                )
            ],
        ]
    )


def format_reminder_text(enabled: bool, remind_time) -> str:
    time_str = remind_time.strftime("%H:%M") if remind_time else "20:00"
    status_text = "✅ Включены" if enabled else "❌ Выключены"

    return (
        "🔔 <b>Уведомления</b>\n\n"
        f"Статус: <b>{status_text}</b>\n"
        f"Время напоминания: <b>{time_str}</b>\n\n"
        "Бот будет присылать напоминание добавить транзакции, "
        "если за текущий день у пользователя ещё нет записей."
    )


@router.message(F.text == "🔔 Уведомления")
async def open_reminders_menu(message: Message):
    user = await db.get_user_by_telegram_id(message.from_user.id)
    if not user:
        user = await db.create_user(
            telegram_id=message.from_user.id,
            username=message.from_user.username,
            first_name=message.from_user.first_name,
        )

    reminder = await db.get_reminder_settings(user["id"])

    await message.answer(
        format_reminder_text(
            enabled=reminder["enabled"],
            remind_time=reminder["remind_time"],
        ),
        reply_markup=reminders_inline_keyboard(reminder["enabled"]),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "reminder_enable")
async def enable_reminders(callback: CallbackQuery):
    user = await db.get_user_by_telegram_id(callback.from_user.id)
    if not user:
        user = await db.create_user(
            telegram_id=callback.from_user.id,
            username=callback.from_user.username,
            first_name=callback.from_user.first_name,
        )

    reminder = await db.set_reminder_enabled(user["id"], True)

    await callback.message.edit_text(
        format_reminder_text(
            enabled=reminder["enabled"],
            remind_time=reminder["remind_time"],
        ),
        reply_markup=reminders_inline_keyboard(reminder["enabled"]),
        parse_mode="HTML",
    )
    await callback.answer("Уведомления включены")


@router.callback_query(F.data == "reminder_disable")
async def disable_reminders(callback: CallbackQuery):
    user = await db.get_user_by_telegram_id(callback.from_user.id)
    if not user:
        user = await db.create_user(
            telegram_id=callback.from_user.id,
            username=callback.from_user.username,
            first_name=callback.from_user.first_name,
        )

    reminder = await db.set_reminder_enabled(user["id"], False)

    await callback.message.edit_text(
        format_reminder_text(
            enabled=reminder["enabled"],
            remind_time=reminder["remind_time"],
        ),
        reply_markup=reminders_inline_keyboard(reminder["enabled"]),
        parse_mode="HTML",
    )
    await callback.answer("Уведомления выключены")


@router.callback_query(F.data == "reminder_status_info")
async def reminder_status_info(callback: CallbackQuery):
    await callback.answer("Здесь показывается текущий статус уведомлений")


@router.callback_query(F.data == "reminder_back")
async def reminder_back(callback: CallbackQuery):
    await callback.message.answer(
        "Вы вернулись в главное меню.",
        reply_markup=main_menu(),
    )
    await callback.answer()