# scripts/generate_test_transactions.py
from __future__ import annotations

import argparse
import asyncio
import os
import random
from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, List, Tuple

import asyncpg
from dotenv import load_dotenv


load_dotenv()


@dataclass
class CategorySpec:
    name: str
    weight: float  # доля расходов


DEFAULT_EXPENSE_CATEGORIES: List[CategorySpec] = [
    CategorySpec("Еда", 0.42),
    CategorySpec("Транспорт", 0.10),
    CategorySpec("Жильё", 0.28),
    CategorySpec("Развлечения", 0.08),
    CategorySpec("Здоровье", 0.06),
    CategorySpec("Покупки", 0.06),
]


DEFAULT_INCOME_CATEGORIES: List[CategorySpec] = [
    CategorySpec("Зарплата", 0.85),
    CategorySpec("Подработка", 0.15),
]


def money(x: float) -> Decimal:
    return Decimal(str(x)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def month_start(dt: datetime) -> datetime:
    return dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def add_months(dt: datetime, months: int) -> datetime:
    y = dt.year + (dt.month - 1 + months) // 12
    m = (dt.month - 1 + months) % 12 + 1
    return dt.replace(year=y, month=m)


def days_in_month(dt: datetime) -> int:
    start = month_start(dt)
    nxt = add_months(start, 1)
    return (nxt - start).days


async def connect_pool() -> asyncpg.Pool:
    host = os.getenv("DB_HOST")
    port = int(os.getenv("DB_PORT", 5432))
    db_name = os.getenv("DB_NAME")
    user = os.getenv("DB_USER")
    password = os.getenv("DB_PASS")

    missing = [k for k, v in [("DB_HOST", host), ("DB_NAME", db_name), ("DB_USER", user), ("DB_PASS", password)] if not v]
    if missing:
        raise RuntimeError(f"Не заданы переменные в .env: {', '.join(missing)}")

    return await asyncpg.create_pool(
        host=host,
        port=port,
        user=user,
        password=password,
        database=db_name,
        min_size=1,
        max_size=5,
    )


async def ensure_user(conn: asyncpg.Connection, telegram_id: int) -> int:
    row = await conn.fetchrow("SELECT id FROM users WHERE telegram_id=$1", telegram_id)
    if row:
        return int(row["id"])

    # создаём пользователя
    # username/first_name можно оставить пустыми
    new_id = await conn.fetchval(
        "INSERT INTO users (telegram_id, username, first_name) VALUES ($1, $2, $3) RETURNING id",
        telegram_id,
        None,
        None,
    )
    return int(new_id)


async def ensure_categories(
    conn: asyncpg.Connection,
    user_id: int,
    specs: List[CategorySpec],
    cat_type: str,
) -> Dict[str, int]:
    """
    Возвращает mapping name -> category_id
    """
    existing = await conn.fetch(
        "SELECT id, name FROM categories WHERE user_id=$1 AND type=$2",
        user_id,
        cat_type,
    )
    mp: Dict[str, int] = {r["name"]: int(r["id"]) for r in existing}

    for spec in specs:
        if spec.name in mp:
            continue
        cid = await conn.fetchval(
            "INSERT INTO categories (user_id, name, type) VALUES ($1, $2, $3) RETURNING id",
            user_id,
            spec.name,
            cat_type,
        )
        mp[spec.name] = int(cid)

    return mp


def pick_day_in_month(rng: random.Random, mstart: datetime) -> datetime:
    dim = days_in_month(mstart)
    day = rng.randint(1, dim)
    hour = rng.randint(9, 21)
    minute = rng.randint(0, 59)
    return mstart.replace(day=day, hour=hour, minute=minute)


def generate_month_amounts(
    rng: random.Random,
    base: float,
    trend_per_month: float,
    month_index: int,
    volatility: float,
) -> float:
    """
    base — стартовый уровень
    trend_per_month — рост/падение в месяц (например 0.03 = +3%)
    volatility — шум (например 0.10 = ±10%)
    """
    level = base * ((1.0 + trend_per_month) ** month_index)
    noise = rng.uniform(-volatility, volatility)
    return max(0.0, level * (1.0 + noise))


def split_by_weights(total: float, specs: List[CategorySpec]) -> List[Tuple[str, float]]:
    # нормируем веса на случай, если не ровно 1.0
    s = sum(c.weight for c in specs)
    weights = [(c.name, c.weight / s) for c in specs]
    return [(name, total * w) for name, w in weights]


def generate_transactions_for_month(
    rng: random.Random,
    user_id: int,
    mstart: datetime,
    cat_map: Dict[str, int],
    month_total: float,
    specs: List[CategorySpec],
    tx_per_category_range: Tuple[int, int],
    tx_noise: float,
    tx_type: str,
) -> List[Tuple[int, int, Decimal, datetime, str, str]]:
    """
    Возвращает список кортежей для INSERT:
      (user_id, category_id, amount, date, type, note)
    """
    rows: List[Tuple[int, int, Decimal, datetime, str, str]] = []
    parts = split_by_weights(month_total, specs)

    for cat_name, cat_total in parts:
        category_id = cat_map[cat_name]
        n_tx = rng.randint(tx_per_category_range[0], tx_per_category_range[1])

        # делим cat_total на n_tx транзакций + шум
        # базовая сумма:
        base_tx = cat_total / max(1, n_tx)

        for _ in range(n_tx):
            amt = base_tx * (1.0 + rng.uniform(-tx_noise, tx_noise))
            amt = max(10.0, amt)  # минимальная сумма
            dt = pick_day_in_month(rng, mstart)

            note = cat_name.lower()
            rows.append((user_id, category_id, money(amt), dt, tx_type, note))

    return rows


async def main():
    parser = argparse.ArgumentParser(description="Генератор тестовых транзакций за последние месяцы.")
    parser.add_argument("--telegram-id", type=int, required=True, help="telegram_id пользователя")
    parser.add_argument("--months", type=int, default=6, help="сколько последних полных месяцев заполнить")
    parser.add_argument("--seed", type=int, default=42, help="seed для воспроизводимости")
    parser.add_argument("--base-expense", type=float, default=85000.0, help="база расходов в месяц (руб)")
    parser.add_argument("--expense-trend", type=float, default=0.02, help="тренд расходов/месяц (0.02 = +2%)")
    parser.add_argument("--expense-volatility", type=float, default=0.10, help="шум по месяцам (0.10 = ±10%)")
    parser.add_argument("--tx-noise", type=float, default=0.35, help="шум внутри транзакций (0.35 = ±35%)")
    parser.add_argument("--min-tx", type=int, default=3, help="мин. транзакций на категорию в месяц")
    parser.add_argument("--max-tx", type=int, default=10, help="макс. транзакций на категорию в месяц")

    parser.add_argument("--with-income", action="store_true", help="генерировать также доходы")
    parser.add_argument("--base-income", type=float, default=120000.0, help="база доходов в месяц (руб)")
    parser.add_argument("--income-trend", type=float, default=0.00, help="тренд доходов/месяц")
    parser.add_argument("--income-volatility", type=float, default=0.03, help="шум доходов по месяцам")

    parser.add_argument(
        "--wipe-generated",
        action="store_true",
        help="перед генерацией удалить все транзакции этого пользователя (ОСТОРОЖНО)",
    )

    args = parser.parse_args()

    rng = random.Random(args.seed)

    pool = await connect_pool()
    async with pool.acquire() as conn:
        user_id = await ensure_user(conn, args.telegram_id)

        if args.wipe_generated:
            await conn.execute("DELETE FROM transactions WHERE user_id=$1", user_id)

        exp_cats = await ensure_categories(conn, user_id, DEFAULT_EXPENSE_CATEGORIES, "expense")
        inc_cats = await ensure_categories(conn, user_id, DEFAULT_INCOME_CATEGORIES, "income") if args.with_income else {}

        now = datetime.now()
        current_m = month_start(now)
        start_m = add_months(current_m, -args.months)  # начало периода
        months_list = [add_months(start_m, i) for i in range(args.months)]  # ровно полные месяцы

        all_rows: List[Tuple[int, int, Decimal, datetime, str, str]] = []

        # расходы
        for i, m in enumerate(months_list):
            month_total = generate_month_amounts(
                rng=rng,
                base=args.base_expense,
                trend_per_month=args.expense_trend,
                month_index=i,
                volatility=args.expense_volatility,
            )
            rows = generate_transactions_for_month(
                rng=rng,
                user_id=user_id,
                mstart=m,
                cat_map=exp_cats,
                month_total=month_total,
                specs=DEFAULT_EXPENSE_CATEGORIES,
                tx_per_category_range=(args.min_tx, args.max_tx),
                tx_noise=args.tx_noise,
                tx_type="expense",
            )
            all_rows.extend(rows)

        # доходы (по желанию)
        if args.with_income:
            for i, m in enumerate(months_list):
                month_total = generate_month_amounts(
                    rng=rng,
                    base=args.base_income,
                    trend_per_month=args.income_trend,
                    month_index=i,
                    volatility=args.income_volatility,
                )
                # доходов обычно меньше транзакций
                rows = generate_transactions_for_month(
                    rng=rng,
                    user_id=user_id,
                    mstart=m,
                    cat_map=inc_cats,
                    month_total=month_total,
                    specs=DEFAULT_INCOME_CATEGORIES,
                    tx_per_category_range=(1, 2),
                    tx_noise=0.05,
                    tx_type="income",
                )
                all_rows.extend(rows)

        # вставка пачкой
        await conn.executemany(
            """
            INSERT INTO transactions (user_id, category_id, amount, date, type, note)
            VALUES ($1, $2, $3, $4, $5, $6)
            """,
            all_rows,
        )

        # краткий отчёт
        created_exp = sum(1 for r in all_rows if r[4] == "expense")
        created_inc = sum(1 for r in all_rows if r[4] == "income")
        print(f"✅ Готово. Пользователь user_id={user_id}.")
        print(f"   Добавлено транзакций: расходы={created_exp}, доходы={created_inc}")
        print(f"   Период: {months_list[0].date()} .. {add_months(months_list[-1], 1).date()} (полные месяцы)")

    await pool.close()


if __name__ == "__main__":
    asyncio.run(main())