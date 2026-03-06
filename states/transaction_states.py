from aiogram.fsm.state import StatesGroup, State

# ==== ДОХОД ====
class IncomeState(StatesGroup):
    choosing_date = State()               # ввод даты
    choosing_time = State()               # ввод времени
    choosing_category = State()           # выбор категории
    entering_custom_category = State()    # ввод новой категории
    entering_amount = State()             # ввод суммы
    entering_note = State()               # комментарий

# ==== РАСХОД ====
class ExpenseState(StatesGroup):
    choosing_date = State()               # ввод даты
    choosing_time = State()               # ввод времени
    choosing_category = State()           # выбор категории
    entering_custom_category = State()    # ввод новой категории
    entering_amount = State()             # ввод суммы
    entering_note = State()               # комментарий
    waiting_for_new_category = State()

# ==== БЫСТРЫЙ ВВОД РАСХОДА ====
class QuickExpenseState(StatesGroup):
    confirming_ml_category = State()
    choosing_manual_category = State()

# ==== УДАЛЕНИЕ ====
class DeleteState(StatesGroup):
    choosing_start_date = State()        # ввод начальной даты
    choosing_end_date = State()          # ввод конечной даты
    confirming = State()                 # подтверждение удаления

# ==== ФИЛЬТР ИСТОРИИ ====
class FilterState(StatesGroup):
    choosing_start_date = State()        # ввод начальной даты
    choosing_end_date = State()          # ввод конечной даты

# ==== АНАЛИТИКА ====
class AnalyticsState(StatesGroup):
    choosing_year = State()
    choosing_start_date = State()
    choosing_end_date = State()