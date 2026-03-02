# handlers/transactions/expense.py
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext
from datetime import datetime

from database.db import db
from database.repository import TransactionRepository
from services.ml.classifier.predict import predict_category
from states.transaction_states import ExpenseState
from utils.keyboards import main_menu, back_keyboard
from .keyboards import quick_date_keyboard, build_category_keyboard, ml_top_keyboard

router = Router()


@router.message(F.text.lower().contains("добавить расход"))
async def start_expense(message: Message, state: FSMContext):
    await state.set_state(ExpenseState.choosing_date)
    await message.answer(
        "Введите дату расхода (ДД.ММ.ГГГГ) или используйте кнопки:",
        reply_markup=quick_date_keyboard(),
    )


@router.message(ExpenseState.choosing_date)
async def expense_date(message: Message, state: FSMContext):
    date = datetime.strptime(message.text.strip(), "%d.%m.%Y").date()
    await state.update_data(date=date)
    await state.set_state(ExpenseState.choosing_time)
    await message.answer("Введите время (ЧЧ:ММ):", reply_markup=back_keyboard())


@router.message(ExpenseState.choosing_time)
async def expense_time(message: Message, state: FSMContext):
    time = datetime.strptime(message.text.strip(), "%H:%M").time()
    data = await state.get_data()
    await state.update_data(datetime=datetime.combine(data["date"], time))
    await state.set_state(ExpenseState.entering_amount)
    await message.answer("Введите сумму расхода:")


@router.message(ExpenseState.entering_amount)
async def expense_amount(message: Message, state: FSMContext):
    await state.update_data(amount=float(message.text.replace(",", ".")))
    await state.set_state(ExpenseState.entering_note)
    await message.answer("Комментарий или '-' :")


@router.message(ExpenseState.entering_note)
async def expense_note(message: Message, state: FSMContext):
    data = await state.get_data()
    note = None if message.text.strip() == "-" else message.text.strip()
    user_id = await TransactionRepository.get_user_id(message.from_user.id)

    # нет note -> ручной выбор
    if not note:
        rows = await db.execute(
            "SELECT name FROM categories WHERE user_id=$1 AND type='expense' ORDER BY name",
            user_id,
            fetch=True,
        )
        categories = [r["name"] for r in rows]

        await state.update_data(note=None)
        await state.set_state(ExpenseState.choosing_category)
        await message.answer(
            "Выберите категорию расхода:",
            reply_markup=build_category_keyboard(categories, "expense_cat_"),
        )
        return

    # ML top-3
    try:
        predicted_name, conf, top = predict_category(note, data["amount"], top_k=3)
    except Exception as e:
        print("ML error:", e)
        predicted_name, conf, top = None, 0.0, []

    if not predicted_name:
        rows = await db.execute(
            "SELECT name FROM categories WHERE user_id=$1 AND type='expense' ORDER BY name",
            user_id,
            fetch=True,
        )
        categories = [r["name"] for r in rows]
        await state.update_data(note=note)
        await state.set_state(ExpenseState.choosing_category)
        await message.answer(
            "Не смог определить категорию. Выберите вручную:",
            reply_markup=build_category_keyboard(categories, "expense_cat_"),
        )
        return

    # Подстраховка: если вдруг пришло число -> ищем в БД
    if isinstance(predicted_name, str) and predicted_name.isdigit():
        maybe_id = int(predicted_name)
        row = await db.execute(
            "SELECT id, name FROM categories WHERE id=$1 AND user_id=$2 AND type='expense'",
            maybe_id,
            user_id,
            fetchrow=True,
        )
        if row:
            predicted_name = row["name"]
            suggested_id = row["id"]
        else:
            suggested_id = None
    else:
        suggested_id = None

    if not suggested_id:
        suggested_id = await TransactionRepository.get_category_id(user_id, predicted_name, "expense")
        if not suggested_id:
            suggested_id = await TransactionRepository.create_category(user_id, predicted_name, "expense")

    await state.update_data(
        note=note,
        suggested_category_id=suggested_id,
        ml_predicted_name=predicted_name,
        ml_confidence=conf,
        ml_top=top,
    )

    if not top:
        top = [(predicted_name, conf)]

    await message.answer(
        "🤖 Выберите категорию (1 клик):",
        reply_markup=ml_top_keyboard(top, max_buttons=3),
    )


@router.callback_query(F.data.startswith("ml_pick|"))
async def ml_pick(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    user_id = await TransactionRepository.get_user_id(callback.from_user.id)

    picked_name = callback.data.split("|", 1)[1].strip()

    cat_id = await TransactionRepository.get_category_id(user_id, picked_name, "expense")
    if not cat_id:
        cat_id = await TransactionRepository.create_category(user_id, picked_name, "expense")

    suggested_id = data.get("suggested_category_id")

    await TransactionRepository.add_transaction(
        user_id=user_id,
        category_id=cat_id,
        amount=data["amount"],
        datetime_=data["datetime"],
        type_="expense",
        note=data.get("note"),
        suggested_category_id=suggested_id,
        is_category_accepted=(cat_id == suggested_id),
    )

    await state.clear()
    await callback.answer()
    await callback.message.answer("💾 <b>Расход сохранён!</b>", reply_markup=main_menu())


@router.callback_query(F.data == "ml_other")
async def ml_other(callback: CallbackQuery, state: FSMContext):
    user_id = await TransactionRepository.get_user_id(callback.from_user.id)
    rows = await db.execute(
        "SELECT name FROM categories WHERE user_id=$1 AND type='expense' ORDER BY name",
        user_id,
        fetch=True,
    )
    categories = [r["name"] for r in rows]

    await state.set_state(ExpenseState.choosing_category)
    await callback.answer()
    await callback.message.answer(
        "Выберите категорию вручную:",
        reply_markup=build_category_keyboard(categories, "expense_cat_"),
    )


@router.callback_query(F.data.startswith("expense_cat_"), ExpenseState.choosing_category)
async def expense_manual_category(callback: CallbackQuery, state: FSMContext):
    category = callback.data.removeprefix("expense_cat_")
    await callback.answer()

    data = await state.get_data()
    user_id = await TransactionRepository.get_user_id(callback.from_user.id)

    cat_id = await TransactionRepository.get_category_id(user_id, category, "expense")
    if not cat_id:
        cat_id = await TransactionRepository.create_category(user_id, category, "expense")

    await TransactionRepository.add_transaction(
        user_id=user_id,
        category_id=cat_id,
        amount=data["amount"],
        datetime_=data["datetime"],
        type_="expense",
        note=data.get("note"),
        suggested_category_id=data.get("suggested_category_id"),
        is_category_accepted=False,
    )

    await state.clear()
    await callback.message.answer("💾 <b>Расход сохранён!</b>", reply_markup=main_menu())
