# handlers/start.py

from aiogram import Router, F
from aiogram.types import Message
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext

from database.db import db
from utils.keyboards import main_menu

router = Router()


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

    await message.answer(
        f"Привет, <b>{message.from_user.first_name}</b>!\n"
        f"Я помогу тебе вести учёт финансов.\n\n"
        f"<b>Теперь доходы и расходы можно вводить одной строкой.</b>\n\n"
        f"<b>Примеры:</b>\n"
        f"<code>+100000 зарплата вчера</code>\n"
        f"<code>+5000 подарок 01.03.2026</code>\n"
        f"<code>-500 бензин сегодня</code>\n"
        f"<code>-1200 кафе вчера 19:30</code>\n\n"
        f"<b>Можно указывать:</b>\n"
        f"• описание\n"
        f"• дату\n"
        f"• время\n\n"
        f"<b>Если дату не указать</b> — будет использована сегодняшняя.\n"
        f"<b>Если время не указать</b> — запись сохранится без указанного времени.",
        reply_markup=main_menu()
    )


@router.message(F.text == "🔙 Назад")
async def go_back(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "🔁 Главное меню:\n\n"
        "Пример быстрого ввода:\n"
        "<code>+100000 зарплата вчера 21:21</code>\n"
        "<code>-500 бензин сегодня</code>",
        reply_markup=main_menu()
    )