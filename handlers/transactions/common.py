# handlers/transactions/common.py
from aiogram import Router, F
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext
from datetime import datetime, timedelta

from states.transaction_states import IncomeState, ExpenseState
from utils.keyboards import back_keyboard

router = Router()


@router.callback_query(F.data.in_(["date_today", "date_yesterday"]))
async def quick_date(callback: CallbackQuery, state: FSMContext):
    state_name = await state.get_state()
    is_income = bool(state_name and state_name.startswith("IncomeState"))

    date = datetime.today().date()
    if callback.data == "date_yesterday":
        date -= timedelta(days=1)

    await state.update_data(date=date)
    await state.set_state(IncomeState.choosing_time if is_income else ExpenseState.choosing_time)

    await callback.message.answer(
        f"🗓 Вы выбрали: <b>{date.strftime('%d.%m.%Y')}</b>\nВведите время (ЧЧ:ММ):",
        reply_markup=back_keyboard(),
    )
    await callback.answer()
