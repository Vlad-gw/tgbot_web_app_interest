# handlers/history.py — история транзакций с ручным вводом дат (ДД.ММ.ГГГГ)

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from datetime import datetime
from states.transaction_states import FilterState
from database.db import db
from utils.keyboards import main_menu, back_keyboard

router = Router()

# 🔹 Шаг 1: вход в историю
@router.message(F.text == "📜 История транзакций")
async def start_history_filter(message: Message, state: FSMContext):
    await state.set_state(FilterState.choosing_start_date)
    await message.answer(
        "📜 История транзакций.\nВведите <b>начальную дату</b> в формате ДД.ММ.ГГГГ:",
        reply_markup=back_keyboard()
    )

# 🔹 Шаг 2: ввод начальной даты
@router.message(FilterState.choosing_start_date)
async def choose_start_date(message: Message, state: FSMContext):
    try:
        start_date = datetime.strptime(message.text.strip(), "%d.%m.%Y").date()
        await state.update_data(start_date=start_date)
        await state.set_state(FilterState.choosing_end_date)

        await message.answer(
            f"Начальная дата: <b>{start_date.strftime('%d.%m.%Y')}</b>\n"
            "Теперь введите <b>конечную дату</b> периода в формате ДД.ММ.ГГГГ:",
            reply_markup=back_keyboard()
        )

    except ValueError:
        await message.answer("❌ Некорректная дата.\nВведите в формате ДД.ММ.ГГГГ.")

# 🔹 Шаг 3: ввод конечной даты и вывод транзакций
@router.message(FilterState.choosing_end_date)
async def choose_end_date(message: Message, state: FSMContext):
    try:
        end_date = datetime.strptime(message.text.strip(), "%d.%m.%Y").date()
        data = await state.get_data()
        start_date = data["start_date"]

        # Проверка диапазона
        if end_date < start_date:
            await message.answer("❌ Конечная дата не может быть раньше начальной.")
            return

        start_dt = datetime.combine(start_date, datetime.min.time())
        end_dt = datetime.combine(end_date, datetime.max.time())

        # Получение транзакций
        user_id = await db.execute(
            "SELECT id FROM users WHERE telegram_id = $1",
            message.from_user.id,
            fetchval=True
        )

        transactions = await db.execute(
            """
            SELECT t.id, t.type, c.name, t.amount, t.date, t.note
            FROM transactions t
            LEFT JOIN categories c ON t.category_id = c.id
            WHERE t.user_id = $1 AND t.date BETWEEN $2 AND $3
            ORDER BY t.date DESC
            """,
            user_id, start_dt, end_dt,
            fetch=True
        )

        await message.answer(
            f"📅 Период:\n<b>{start_date.strftime('%d.%m.%Y')} — {end_date.strftime('%d.%m.%Y')}</b>"
        )

        if not transactions:
            await message.answer("❌ Нет транзакций за выбранный период.", reply_markup=main_menu())
            await state.clear()
            return

        # Вывод транзакций и кнопок удаления
        for tx in transactions:
            tx_type = "Доход" if tx["type"] == "income" else "Расход"
            text = (
                f"<b>{tx_type}</b> | {tx['name']} | {tx['amount']} ₽\n"
                f"📅 {tx['date'].strftime('%d.%m.%Y %H:%M')}"
            )

            if tx["note"]:
                text += f"\n💬 {tx['note']}"

            delete_btn = InlineKeyboardMarkup(
                inline_keyboard=[
                    [InlineKeyboardButton(text="🗑 Удалить", callback_data=f"delete_txn_{tx['id']}")]
                ]
            )

            await message.answer(text, reply_markup=delete_btn)

        await state.clear()

    except ValueError:
        await message.answer("❌ Некорректная дата.\nВведите конечную дату в формате ДД.ММ.ГГГГ.")

# 🔹 Удаление транзакции
@router.callback_query(F.data.startswith("delete_txn_"))
async def delete_transaction(callback: CallbackQuery):
    txn_id = int(callback.data.removeprefix("delete_txn_"))

    await db.execute(
        "DELETE FROM transactions WHERE id = $1",
        txn_id,
        execute=True
    )

    await callback.answer("Удалено")
    await callback.message.edit_text("🗑 Транзакция удалена.")

# 🔙 Назад
@router.message(F.text == "🔙 Назад")
async def go_back_history(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("🔁 Главное меню:", reply_markup=main_menu())
