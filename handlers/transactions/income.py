# handlers/transactions/income.py
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from datetime import datetime

from database.db import db
from database.repository import TransactionRepository
from states.transaction_states import IncomeState
from utils.keyboards import main_menu, back_keyboard
from .keyboards import quick_date_keyboard, build_category_keyboard

router = Router()


@router.message(F.text.lower().contains("добавить доход"))
async def start_income(message: Message, state: FSMContext):
    await state.set_state(IncomeState.choosing_date)
    await message.answer(
        "Введите дату дохода (ДД.ММ.ГГГГ) или используйте кнопки:",
        reply_markup=quick_date_keyboard(),
    )


@router.message(IncomeState.choosing_date)
async def income_date(message: Message, state: FSMContext):
    date = datetime.strptime(message.text.strip(), "%d.%m.%Y").date()
    await state.update_data(date=date)
    await state.set_state(IncomeState.choosing_time)
    await message.answer("Введите время (ЧЧ:ММ):", reply_markup=back_keyboard())


@router.message(IncomeState.choosing_time)
async def income_time(message: Message, state: FSMContext):
    time = datetime.strptime(message.text.strip(), "%H:%M").time()
    data = await state.get_data()
    await state.update_data(datetime=datetime.combine(data["date"], time))

    user_id = await TransactionRepository.get_user_id(message.from_user.id)
    rows = await db.execute(
        "SELECT name FROM categories WHERE user_id=$1 AND type='income' ORDER BY name",
        user_id,
        fetch=True,
    )
    categories = [r["name"] for r in rows]

    await state.set_state(IncomeState.choosing_category)
    await message.answer(
        "Выберите категорию дохода:",
        reply_markup=build_category_keyboard(categories, "income_cat_"),
    )


@router.callback_query(F.data.startswith("income_cat_"), IncomeState.choosing_category)
async def income_category(callback: CallbackQuery, state: FSMContext):
    category = callback.data.removeprefix("income_cat_")
    await callback.answer()

    if category == "Другое":
        await state.set_state(IncomeState.entering_custom_category)
        await callback.message.answer("Введите название новой категории:")
        return

    await state.update_data(category_name=category)
    await state.set_state(IncomeState.entering_amount)
    await callback.message.answer("Введите сумму дохода:")


@router.message(IncomeState.entering_custom_category)
async def income_custom_category(message: Message, state: FSMContext):
    user_id = await TransactionRepository.get_user_id(message.from_user.id)
    cat_id = await TransactionRepository.create_category(user_id, message.text.strip(), "income")
    await state.update_data(category_id=cat_id)
    await state.set_state(IncomeState.entering_amount)
    await message.answer("Введите сумму дохода:")


@router.message(IncomeState.entering_amount)
async def income_amount(message: Message, state: FSMContext):
    await state.update_data(amount=float(message.text.replace(",", ".")))
    await state.set_state(IncomeState.entering_note)
    await message.answer("Комментарий или '-' :")


@router.message(IncomeState.entering_note)
async def income_note(message: Message, state: FSMContext):
    data = await state.get_data()
    note = None if message.text.strip() == "-" else message.text.strip()
    user_id = await TransactionRepository.get_user_id(message.from_user.id)

    cat_id = data.get("category_id") or await TransactionRepository.get_category_id(
        user_id, data["category_name"], "income"
    )

    await TransactionRepository.add_transaction(
        user_id=user_id,
        category_id=cat_id,
        amount=data["amount"],
        datetime_=data["datetime"],
        type_="income",
        note=note,
    )

    await state.clear()
    await message.answer("💾 <b>Доход сохранён!</b>", reply_markup=main_menu())
