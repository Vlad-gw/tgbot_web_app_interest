from aiogram.fsm.state import StatesGroup, State

# ==== ДОХОД ====
class IncomeState(StatesGroup):
    choosing_date = State()
    choosing_time = State()
    choosing_category = State()
    entering_custom_category = State()
    entering_amount = State()
    entering_note = State()

# ==== РАСХОД ====
class ExpenseState(StatesGroup):
    choosing_date = State()
    choosing_time = State()
    choosing_category = State()
    entering_custom_category = State()
    entering_amount = State()
    entering_note = State()
    waiting_for_new_category = State()

# ==== БЫСТРЫЙ ВВОД РАСХОДА ====
class QuickExpenseState(StatesGroup):
    confirming_ml_category = State()
    choosing_manual_category = State()

# ==== УДАЛЕНИЕ ====
class DeleteState(StatesGroup):
    choosing_start_date = State()
    choosing_end_date = State()
    confirming = State()

# ==== ФИЛЬТР ИСТОРИИ ====
class FilterState(StatesGroup):
    choosing_start_date = State()
    choosing_end_date = State()

# ==== АНАЛИТИКА ====
class AnalyticsState(StatesGroup):
    choosing_year = State()
    choosing_start_date = State()
    choosing_end_date = State()

# ==== ИМПОРТ ВЫПИСКИ ====
class StatementImportState(StatesGroup):
    choosing_bank = State()
    waiting_for_file = State()
    confirming_import = State()