# handlers/delete.py — удаление транзакций с ручным вводом дат (ДД.ММ.ГГГГ)

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from datetime import datetime
from states.transaction_states import DeleteState
from database.db import db
from utils.keyboards import main_menu, back_keyboard

router = Router()

# 🔹 Шаг 1: выбор начальной даты
@router.message(F.text == "🗑 Удаление транзакций")
async def start_deletion(message: Message, state: FSMContext):
    await state.set_state(DeleteState.choosing_start_date)
    await message.answer(
        "🗑 Введите <b>начальную дату</b> для удаления (ДД.ММ.ГГГГ):",
        reply_markup=back_keyboard()
    )

# 🔹 Шаг 2: ввод начальной даты
@router.message(DeleteState.choosing_start_date)
async def delete_start_date(message: Message, state: FSMContext):
    try:
        start_date = datetime.strptime(message.text.strip(), "%d.%m.%Y").date()
        await state.update_data(start_date=start_date)
        await state.set_state(DeleteState.choosing_end_date)

        await message.answer(
            f"Начальная дата: <b>{start_date.strftime('%d.%m.%Y')}</b>\n"
            "Теперь введите <b>конечную дату</b> (ДД.ММ.ГГГГ):",
            reply_markup=back_keyboard()
        )

    except ValueError:
        await message.answer("❌ Некорректная дата.\nВведите в формате ДД.ММ.ГГГГ.")

# 🔹 Шаг 3: ввод конечной даты
@router.message(DeleteState.choosing_end_date)
async def delete_end_date(message: Message, state: FSMContext):
    try:
        end_date = datetime.strptime(message.text.strip(), "%d.%m.%Y").date()
        data = await state.get_data()
        start_date = data["start_date"]

        if end_date < start_date:
            await message.answer("❌ Конечная дата не может быть раньше начальной.")
            return

        await state.update_data(end_date=end_date)

        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(text="✅ Да", callback_data="confirm_delete"),
                    InlineKeyboardButton(text="❌ Нет", callback_data="cancel_delete")
                ]
            ]
        )

        await state.set_state(DeleteState.confirming)
        await message.answer(
            f"Вы уверены, что хотите удалить транзакции\n"
            f"📅 <b>{start_date.strftime('%d.%m.%Y')} — {end_date.strftime('%d.%m.%Y')}</b>?",
            reply_markup=keyboard
        )

    except ValueError:
        await message.answer("❌ Некорректная дата.\nВведите дату в формате ДД.ММ.ГГГГ.")

# 🔹 Шаг 4: подтверждение удаления
@router.callback_query(F.data == "confirm_delete", DeleteState.confirming)
async def confirm_delete(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()

    start_dt = datetime.combine(data["start_date"], datetime.min.time())
    end_dt = datetime.combine(data["end_date"], datetime.max.time())

    user_id = await db.execute(
        "SELECT id FROM users WHERE telegram_id = $1",
        callback.from_user.id,
        fetchval=True
    )

    deleted_rows = await db.execute(
        "DELETE FROM transactions WHERE user_id = $1 AND date BETWEEN $2 AND $3 RETURNING id",
        user_id, start_dt, end_dt,
        fetch=True
    )

    count = len(deleted_rows)

    await state.clear()
    await callback.message.answer(
        f"🗑 Удалено транзакций: <b>{count}</b>",
        reply_markup=main_menu()
    )

# 🔹 Шаг 5: отмена
@router.callback_query(F.data == "cancel_delete", DeleteState.confirming)
async def cancel_delete(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.answer("Отменено")
    await callback.message.answer("❌ Удаление отменено.", reply_markup=main_menu())

# 🔙 Назад
@router.message(F.text == "🔙 Назад")
async def go_back_delete(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("🔁 Главное меню:", reply_markup=main_menu())
