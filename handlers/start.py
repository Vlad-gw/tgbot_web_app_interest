# handlers/start.py

import os

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext

from database.db import db
from utils.keyboards import main_menu, mini_app_inline_keyboard

router = Router()


def _get_mini_app_url() -> str:
    base_url = os.getenv("MINI_APP_URL", "").strip().rstrip("/")
    if not base_url:
        base_url = os.getenv("SITE_URL", "http://127.0.0.1:8000").strip().rstrip("/")
    return f"{base_url}/miniapp/"


def _is_https_url(url: str) -> bool:
    return url.startswith("https://")


def _start_text(first_name: str, mini_app_ready: bool) -> str:
    mini_app_text = (
        "Нажми кнопку <b>под сообщением</b> — <b>📱 Открыть Mini App</b>."
        if mini_app_ready
        else "Mini App пока не активен, потому что для Telegram нужен <b>HTTPS URL</b>."
    )

    return (
        f"Привет, <b>{first_name}</b>!\n"
        f"Я помогу тебе вести учёт финансов.\n\n"
        f"<b>Быстрый ввод транзакций:</b>\n"
        f"<code>+100000 зарплата вчера</code>\n"
        f"<code>+5000 подарок 01.03.2026</code>\n"
        f"<code>-500 бензин сегодня</code>\n"
        f"<code>-1200 кафе вчера 19:30</code>\n\n"
        f"<b>Mini App:</b>\n"
        f"{mini_app_text}\n\n"
        f"<b>Если дату не указать</b> — будет использована сегодняшняя.\n"
        f"<b>Если время не указать</b> — запись сохранится без указанного времени."
    )


@router.message(CommandStart())
async def cmd_start(message: Message):
    tg_id = message.from_user.id

    user = await db.execute(
        "SELECT id FROM users WHERE telegram_id = $1",
        tg_id,
        fetchval=True
    )
    if not user:
        await db.execute(
            "INSERT INTO users (telegram_id, username, first_name) VALUES ($1, $2, $3)",
            tg_id,
            message.from_user.username,
            message.from_user.first_name,
            execute=True
        )

    mini_app_ready = _is_https_url(_get_mini_app_url())

    await message.answer(
        _start_text(message.from_user.first_name, mini_app_ready),
        reply_markup=main_menu()
    )

    await message.answer(
        "Открыть Mini App:",
        reply_markup=mini_app_inline_keyboard()
    )


@router.message(F.text == "🔙 Назад")
async def go_back(message: Message, state: FSMContext):
    await state.clear()

    mini_app_ready = _is_https_url(_get_mini_app_url())

    await message.answer(
        "🔁 Главное меню:\n\n"
        "Пример быстрого ввода:\n"
        "<code>+100000 зарплата вчера 21:21</code>\n"
        "<code>-500 бензин сегодня</code>\n\n"
        + (
            "Для Mini App используй кнопку <b>под сообщением</b>."
            if mini_app_ready
            else "Mini App пока не включён: нужен <b>HTTPS</b>."
        ),
        reply_markup=main_menu()
    )

    await message.answer(
        "Открыть Mini App:",
        reply_markup=mini_app_inline_keyboard()
    )


@router.message(F.text == "📱 Mini App")
async def mini_app_hint(message: Message):
    await message.answer(
        "Используй кнопку <b>под сообщением</b> — <b>📱 Открыть Mini App</b>.",
        reply_markup=mini_app_inline_keyboard()
    )


@router.callback_query(F.data == "miniapp_https_required")
async def miniapp_https_required(callback: CallbackQuery):
    await callback.answer(
        "Mini App пока недоступен: нужен HTTPS URL.",
        show_alert=True
    )