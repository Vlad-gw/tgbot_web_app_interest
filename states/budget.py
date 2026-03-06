# states/budget.py
from aiogram.fsm.state import StatesGroup, State


class BudgetStates(StatesGroup):
    choosing_category = State()
    entering_custom_category = State()
    entering_amount = State()