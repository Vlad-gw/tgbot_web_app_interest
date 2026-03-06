# handlers/budget.py
from __future__ import annotations

from datetime import datetime, date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Dict, List, Tuple

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery
from aiogram.fsm.context import FSMContext

from database.db import db
from states.budget import BudgetStates
from utils.budget_keyboards import categories_inline_keyboard
from utils.keyboards import main_menu

router = Router()


RU_MONTHS = {
    1: "Январь",
    2: "Февраль",
    3: "Март",
    4: "Апрель",
    5: "Май",
    6: "Июнь",
    7: "Июль",
    8: "Август",
    9: "Сентябрь",
    10: "Октябрь",
    11: "Ноябрь",
    12: "Декабрь",
}


def _month_start_date(dt: datetime) -> date:
    return dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0).date()


def _add_months(d: date, months: int) -> date:
    y = d.year + (d.month - 1 + months) // 12
    m = (d.month - 1 + months) % 12 + 1
    return date(y, m, 1)


def _format_month_ru(month_date: date) -> str:
    return f"{RU_MONTHS.get(month_date.month, str(month_date.month))} {month_date.year}"


def _format_rub(amount: Decimal) -> str:
    n = int(amount.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    return f"{n:,} ₽".replace(",", " ")


def _safe_decimal(x) -> Decimal:
    if x is None:
        return Decimal("0")
    if isinstance(x, Decimal):
        return x
    return Decimal(str(x))


def _emoji_for_category(name: str) -> str:
    n = (name or "").strip().lower()

    food = ["еда", "продукт", "кафе", "ресторан", "фаст", "доставка", "пицц", "бургер", "суш"]
    if any(k in n for k in food):
        return "🍔"

    transport = ["транспорт", "такси", "метро", "автобус", "трам", "поезд", "бенз", "азс", "парков"]
    if any(k in n for k in transport):
        return "🚗"

    home = ["жиль", "аренд", "кварт", "дом", "коммун", "жкх", "свет", "вода", "газ", "интернет"]
    if any(k in n for k in home):
        return "🏠"

    health = ["здоров", "аптек", "врач", "лекар", "стомат", "анализ"]
    if any(k in n for k in health):
        return "💊"

    shop = ["покуп", "одеж", "обув", "магаз", "маркет", "wb", "wildberries", "ozon", "озон", "ламода"]
    if any(k in n for k in shop):
        return "🛍"

    fun = ["развлеч", "кино", "игр", "подпис", "музык", "steam", "netflix", "spotify"]
    if any(k in n for k in fun):
        return "🎮"

    edu = ["учеб", "курс", "обуч", "универ", "книг"]
    if any(k in n for k in edu):
        return "📚"

    return "🧾"


def _is_bad_category_name(name: str) -> bool:
    """
    Убираем мусор вроде '2', пустых строк и т.п.
    """
    s = (name or "").strip()
    if not s:
        return True
    if len(s) < 2:
        return True
    if s.isdigit():
        return True
    return False


async def _get_user_id(telegram_id: int) -> int | None:
    q = "SELECT id FROM users WHERE telegram_id = $1"
    return await db.execute(q, telegram_id, fetchval=True)


async def _get_expense_categories(user_id: int) -> list[tuple[int, str]]:
    q = """
        SELECT id, name
        FROM categories
        WHERE user_id = $1 AND type = 'expense'
        ORDER BY name
    """
    rows = await db.execute(q, user_id, fetch=True)
    cats = [(int(r["id"]), str(r["name"])) for r in rows]
    # ✅ фильтр мусора (в том числе "2")
    cats = [(cid, name) for cid, name in cats if not _is_bad_category_name(name)]
    return cats


async def _get_category_name(category_id: int) -> str:
    q = "SELECT name FROM categories WHERE id=$1"
    name = await db.execute(q, category_id, fetchval=True)
    return str(name) if name else "Категория"


async def _get_or_create_expense_category(user_id: int, name: str) -> int:
    """
    Если категория уже есть у пользователя (case-insensitive) — возвращаем id.
    Иначе создаём новую expense-категорию.
    """
    clean = name.strip()

    q_find = """
        SELECT id
        FROM categories
        WHERE user_id=$1 AND type='expense' AND LOWER(name)=LOWER($2)
        LIMIT 1
    """
    existing = await db.execute(q_find, user_id, clean, fetchval=True)
    if existing:
        return int(existing)

    q_ins = """
        INSERT INTO categories (user_id, name, type)
        VALUES ($1, $2, 'expense')
        RETURNING id
    """
    new_id = await db.execute(q_ins, user_id, clean, fetchval=True)
    return int(new_id)


async def _fetch_budgets_for_month(user_id: int, month_date: date) -> List[dict]:
    q = """
        SELECT
            b.category_id,
            COALESCE(c.name, 'Без категории') AS category_name,
            b.limit_amount
        FROM budgets b
        LEFT JOIN categories c ON c.id = b.category_id
        WHERE b.user_id = $1 AND b.month = $2
        ORDER BY category_name
    """
    rows = await db.execute(q, user_id, month_date, fetch=True)
    return [dict(r) for r in rows]


async def _fetch_spent_by_category(user_id: int, month_date: date) -> Dict[int, Decimal]:
    start_dt = datetime(month_date.year, month_date.month, 1)
    next_month = _add_months(month_date, 1)
    end_dt = datetime(next_month.year, next_month.month, 1)

    q = """
        SELECT
            COALESCE(t.category_id, 0) AS category_id,
            COALESCE(SUM(t.amount), 0) AS spent
        FROM transactions t
        WHERE
            t.user_id = $1
            AND t.type = 'expense'
            AND t.date >= $2
            AND t.date < $3
        GROUP BY 1
    """
    rows = await db.execute(q, user_id, start_dt, end_dt, fetch=True)
    mp: Dict[int, Decimal] = {}
    for r in rows:
        mp[int(r["category_id"])] = _safe_decimal(r["spent"])
    return mp


def _build_budget_report_text(month_str: str, budgets: List[dict], spent_map: Dict[int, Decimal]) -> str:
    if not budgets:
        return (
            f"📊 <b>Бюджет на {month_str}</b>\n\n"
            "Пока нет установленных лимитов по категориям.\n"
            "Нажми 🎯 <b>Установить бюджет</b> и задай лимит хотя бы для одной категории."
        )

    lines: List[str] = [f"📊 <b>Бюджет на {month_str}</b>\n"]

    total_limit = Decimal("0")
    total_spent = Decimal("0")

    for b in budgets:
        cid = int(b["category_id"])
        cname = str(b["category_name"])
        limit_amt = _safe_decimal(b["limit_amount"])
        spent_amt = spent_map.get(cid, Decimal("0"))

        left = limit_amt - spent_amt

        total_limit += limit_amt
        total_spent += spent_amt

        emoji = _emoji_for_category(cname)
        if left >= 0:
            status = f"✅ Осталось: <b>{_format_rub(left)}</b>"
        else:
            status = f"⚠️ Перерасход: <b>{_format_rub(abs(left))}</b>"

        lines.append(
            f"{emoji} <b>{cname}</b>\n"
            f"   Лимит: {_format_rub(limit_amt)} | Потрачено: {_format_rub(spent_amt)}\n"
            f"   {status}\n"
        )

    total_left = total_limit - total_spent
    if total_left >= 0:
        total_status = f"✅ Запас по бюджету: <b>{_format_rub(total_left)}</b>"
    else:
        total_status = f"⚠️ Общий перерасход: <b>{_format_rub(abs(total_left))}</b>"

    lines.append(
        "—" * 24 + "\n"
        f"💰 <b>Итого лимит:</b> {_format_rub(total_limit)}\n"
        f"💸 <b>Итого потрачено:</b> {_format_rub(total_spent)}\n"
        f"{total_status}"
    )

    return "\n".join(lines)


@router.message(F.text == "🎯 Установить бюджет")
async def start_budget_setup(message: Message, state: FSMContext):
    telegram_id = message.from_user.id
    user_id = await _get_user_id(telegram_id)
    if not user_id:
        await message.answer("❌ Пользователь не найден в базе. Нажми /start.")
        return

    categories = await _get_expense_categories(user_id)

    await state.clear()
    await state.update_data(month=_month_start_date(datetime.now()))
    await state.set_state(BudgetStates.choosing_category)

    await message.answer(
        "🎯 <b>Установка бюджета</b>\n\n"
        "Выберите категорию расхода:",
        reply_markup=categories_inline_keyboard(categories),
    )


@router.callback_query(F.data == "budget_cancel")
async def budget_cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.answer("✅ Отменено.", reply_markup=main_menu())
    await callback.answer()


# ✅ НОВОЕ: Аналитика бюджета (та же таблица, что после добавления бюджета)
@router.callback_query(F.data == "budget_analytics")
async def budget_analytics(callback: CallbackQuery, state: FSMContext):
    telegram_id = callback.from_user.id
    user_id = await _get_user_id(telegram_id)
    if not user_id:
        await callback.message.answer("❌ Пользователь не найден в базе. Нажми /start.")
        await callback.answer()
        return

    data = await state.get_data()
    month_date: date | None = data.get("month")
    if not month_date:
        month_date = _month_start_date(datetime.now())

    month_str = _format_month_ru(month_date)
    budgets = await _fetch_budgets_for_month(user_id, month_date)
    spent_map = await _fetch_spent_by_category(user_id, month_date)
    report_text = _build_budget_report_text(month_str, budgets, spent_map)

    await callback.message.answer(report_text)
    await callback.answer()


@router.callback_query(F.data == "budget_other")
async def budget_other(callback: CallbackQuery, state: FSMContext):
    await state.set_state(BudgetStates.entering_custom_category)
    await callback.message.answer(
        "➕ <b>Другая категория</b>\n\n"
        "Введите название категории (например: <code>Долг</code> или <code>Озон</code>).\n"
        "Чтобы отменить — напишите <b>Отмена</b>.",
    )
    await callback.answer()


@router.message(BudgetStates.entering_custom_category)
async def budget_enter_custom_category(message: Message, state: FSMContext):
    text = (message.text or "").strip()

    if text.lower() in ("отмена", "cancel", "стоп"):
        await state.clear()
        await message.answer("✅ Отменено.", reply_markup=main_menu())
        return

    # базовая валидация
    if _is_bad_category_name(text):
        await message.answer("❌ Название некорректное. Введите нормальное название, например: <code>Долг</code>")
        return

    telegram_id = message.from_user.id
    user_id = await _get_user_id(telegram_id)
    if not user_id:
        await state.clear()
        await message.answer("❌ Пользователь не найден. Нажми /start.", reply_markup=main_menu())
        return

    # создаём/находим категорию
    category_id = await _get_or_create_expense_category(user_id, text)
    await state.update_data(category_id=category_id)
    await state.set_state(BudgetStates.entering_amount)

    cat_name = await _get_category_name(category_id)
    await message.answer(
        f"🧾 Категория: <b>{cat_name}</b>\n"
        f"Введите лимит на месяц в рублях.\n"
        f"Пример: <code>35000</code>\n\n"
        f"Чтобы отменить — напишите <b>Отмена</b>.",
    )


@router.callback_query(F.data.startswith("budget_cat_"))
async def budget_choose_category(callback: CallbackQuery, state: FSMContext):
    cat_id_str = callback.data.replace("budget_cat_", "")
    try:
        category_id = int(cat_id_str)
    except ValueError:
        await callback.answer("Ошибка выбора категории", show_alert=True)
        return

    await state.update_data(category_id=category_id)
    await state.set_state(BudgetStates.entering_amount)

    cat_name = await _get_category_name(category_id)

    await callback.message.answer(
        f"🧾 Категория: <b>{cat_name}</b>\n"
        f"Введите лимит на месяц в рублях.\n"
        f"Пример: <code>35000</code>\n\n"
        f"Чтобы отменить — напишите <b>Отмена</b> или нажмите ❌ Отмена.",
    )
    await callback.answer()


@router.message(BudgetStates.entering_amount)
async def budget_enter_amount(message: Message, state: FSMContext):
    text = (message.text or "").strip()

    if text.lower() in ("отмена", "cancel", "стоп"):
        await state.clear()
        await message.answer("✅ Отменено.", reply_markup=main_menu())
        return

    raw = text.replace(" ", "").replace(",", ".")
    try:
        amount = Decimal(raw)
    except InvalidOperation:
        await message.answer("❌ Некорректная сумма. Введите число, например: <code>35000</code>")
        return

    if amount <= 0:
        await message.answer("❌ Сумма должна быть больше 0. Введите число, например: <code>35000</code>")
        return

    data = await state.get_data()
    month_date: date | None = data.get("month")
    category_id: int | None = data.get("category_id")

    if not month_date or not category_id:
        await state.clear()
        await message.answer("❌ Состояние сбилось. Попробуйте ещё раз.", reply_markup=main_menu())
        return

    telegram_id = message.from_user.id
    user_id = await _get_user_id(telegram_id)
    if not user_id:
        await state.clear()
        await message.answer("❌ Пользователь не найден. Нажми /start.", reply_markup=main_menu())
        return

    # сохраняем бюджет
    q = """
        INSERT INTO budgets (user_id, category_id, month, limit_amount)
        VALUES ($1, $2, $3, $4)
        ON CONFLICT (user_id, category_id, month)
        DO UPDATE SET limit_amount = EXCLUDED.limit_amount
    """
    await db.execute(q, user_id, int(category_id), month_date, amount, execute=True)

    cat_name = await _get_category_name(int(category_id))
    month_str = _format_month_ru(month_date)

    budgets = await _fetch_budgets_for_month(user_id, month_date)
    spent_map = await _fetch_spent_by_category(user_id, month_date)
    report_text = _build_budget_report_text(month_str, budgets, spent_map)

    await state.clear()

    await message.answer(
        "✅ <b>Лимит сохранён</b>\n"
        f"Категория: <b>{cat_name}</b>\n"
        f"Месяц: <b>{month_str}</b>\n"
        f"Лимит: <b>{_format_rub(amount)}</b>",
        reply_markup=main_menu(),
    )
    await message.answer(report_text)