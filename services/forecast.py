# services/forecast.py
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import List, Optional, Tuple

from database.db import db
from services.forecast_math import build_forecast_text


@dataclass
class MonthPoint:
    month_start: datetime
    total: Decimal


def _month_start(dt: datetime) -> datetime:
    return dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def _add_months(dt: datetime, months: int) -> datetime:
    y = dt.year + (dt.month - 1 + months) // 12
    m = (dt.month - 1 + months) % 12 + 1
    return dt.replace(year=y, month=m)


def _normalize_name(s: str) -> str:
    return (s or "").strip().lower()


def _emoji_for_category(name: str) -> str:
    n = _normalize_name(name)

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

    shop = ["одеж", "обув", "магаз", "маркет", "покуп", "wb", "wildberries", "ozon", "ламода"]
    if any(k in n for k in shop):
        return "🛍"

    fun = ["развлеч", "кино", "игр", "подпис", "музык", "steam", "netflix", "spotify"]
    if any(k in n for k in fun):
        return "🎮"

    edu = ["учеб", "курс", "обуч", "универ", "книг"]
    if any(k in n for k in edu):
        return "📚"

    return ""


async def _get_user_id(telegram_id: int) -> Optional[int]:
    q = "SELECT id FROM users WHERE telegram_id = $1"
    return await db.execute(q, telegram_id, fetchval=True)


async def get_monthly_expenses(
    telegram_id: int,
    months_back: int = 12,
    only_full_months: bool = True,
) -> List[MonthPoint]:
    user_id = await _get_user_id(telegram_id)
    if not user_id:
        return []

    now = datetime.now()
    current_month = _month_start(now)

    end = current_month if only_full_months else now
    start = _add_months(current_month, -months_back)

    q = """
        SELECT
            date_trunc('month', t.date) AS month_start,
            COALESCE(SUM(t.amount), 0) AS total
        FROM transactions t
        WHERE
            t.user_id = $1
            AND t.type = 'expense'
            AND t.date >= $2
            AND t.date < $3
        GROUP BY 1
        ORDER BY 1
    """
    rows = await db.execute(q, user_id, start, end, fetch=True)

    res: List[MonthPoint] = []
    for r in rows:
        res.append(MonthPoint(month_start=r["month_start"], total=r["total"]))
    return res


async def get_top_category_for_month(
    user_id: int,
    month_start: datetime,
    month_end: datetime,
) -> Tuple[Optional[str], Optional[int], Optional[int]]:
    """
    Возвращает:
      (pretty_name_with_emoji, share_of_expenses_pct, category_id)
    для заданного месяца.
    """
    q_total = """
        SELECT COALESCE(SUM(t.amount), 0) AS total
        FROM transactions t
        WHERE
            t.user_id = $1
            AND t.type = 'expense'
            AND t.date >= $2
            AND t.date < $3
    """
    total: Decimal = await db.execute(q_total, user_id, month_start, month_end, fetchval=True)
    if not total or total == 0:
        return None, None, None

    q_top = """
        SELECT
            COALESCE(c.id, 0) AS category_id,
            COALESCE(c.name, 'Без категории') AS name,
            COALESCE(SUM(t.amount), 0) AS cat_total
        FROM transactions t
        LEFT JOIN categories c ON c.id = t.category_id
        WHERE
            t.user_id = $1
            AND t.type = 'expense'
            AND t.date >= $2
            AND t.date < $3
        GROUP BY 1, 2
        ORDER BY cat_total DESC
        LIMIT 1
    """
    row = await db.execute(q_top, user_id, month_start, month_end, fetchrow=True)
    if not row:
        return None, None, None

    category_id: int = row["category_id"]
    name: str = row["name"]
    cat_total: Decimal = row["cat_total"]

    share = int(((cat_total / total) * Decimal("100")).quantize(Decimal("1")))

    emoji = _emoji_for_category(name)
    # ВАЖНО: без .strip(), чтобы не "съедать" пробел и не клеить эмодзи к тексту
    pretty = f"{emoji} {name}" if emoji else name

    return pretty, share, (category_id if category_id != 0 else None)


async def get_budget_share_for_category(
    user_id: int,
    category_id: Optional[int],
    month_date,
) -> Optional[int]:
    """
    budget_share = (лимит категории / сумма лимитов всех категорий) * 100
    Колонка: limit_amount
    """
    if not category_id:
        return None

    q_sum_limits = """
        SELECT COALESCE(SUM(b.limit_amount), 0) AS total_limit
        FROM budgets b
        WHERE b.user_id = $1 AND b.month = $2
    """
    total_limit: Decimal = await db.execute(q_sum_limits, user_id, month_date, fetchval=True)
    if not total_limit or total_limit == 0:
        return None

    q_cat_limit = """
        SELECT COALESCE(SUM(b.limit_amount), 0) AS cat_limit
        FROM budgets b
        WHERE b.user_id = $1 AND b.month = $2 AND b.category_id = $3
    """
    cat_limit: Decimal = await db.execute(q_cat_limit, user_id, month_date, category_id, fetchval=True)
    if not cat_limit or cat_limit == 0:
        return None

    share = int(((cat_limit / total_limit) * Decimal("100")).quantize(Decimal("1")))
    return share


async def build_expense_forecast_message(telegram_id: int) -> str:
    user_id = await _get_user_id(telegram_id)
    if not user_id:
        return "📈 Прогноз расходов\n\nПользователь не найден в базе."

    monthly = await get_monthly_expenses(telegram_id=telegram_id, months_back=12, only_full_months=True)
    monthly_totals = [p.total for p in monthly]

    top_name = None
    top_share = None
    top_category_id = None
    budget_share_pct = None

    if monthly:
        last_month_start = monthly[-1].month_start
        last_month_end = _add_months(last_month_start, 1)

        top_name, top_share, top_category_id = await get_top_category_for_month(
            user_id=user_id,
            month_start=last_month_start,
            month_end=last_month_end,
        )

        budget_share_pct = await get_budget_share_for_category(
            user_id=user_id,
            category_id=top_category_id,
            month_date=last_month_start.date(),
        )

    return build_forecast_text(
        monthly_expenses=monthly_totals,
        top_category_name=top_name,
        top_category_share_pct=top_share,
        budget_share_pct=budget_share_pct,
    )