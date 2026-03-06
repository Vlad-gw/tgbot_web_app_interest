# scripts/generate_test_budgets.py
from __future__ import annotations

import argparse
import asyncio
import os
import random
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, List, Tuple

import asyncpg
from dotenv import load_dotenv

load_dotenv()


def money(x: float) -> Decimal:
    return Decimal(str(x)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def month_start(dt: datetime) -> datetime:
    return dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def add_months(dt: datetime, months: int) -> datetime:
    y = dt.year + (dt.month - 1 + months) // 12
    m = (dt.month - 1 + months) % 12 + 1
    return dt.replace(year=y, month=m)


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


async def get_user_id(conn: asyncpg.Connection, telegram_id: int) -> int:
    uid = await conn.fetchval("SELECT id FROM users WHERE telegram_id=$1", telegram_id)
    if not uid:
        raise RuntimeError("Пользователь не найден в таблице users. Сначала сгенерируй транзакции.")
    return int(uid)


async def get_expense_categories(conn: asyncpg.Connection, user_id: int) -> List[Tuple[int, str]]:
    rows = await conn.fetch(
        "SELECT id, name FROM categories WHERE user_id=$1 AND type='expense' ORDER BY id",
        user_id,
    )
    return [(int(r["id"]), str(r["name"])) for r in rows]


def default_budget_weights() -> Dict[str, float]:
    # можно потом настроить под себя
    return {
        "Еда": 0.30,
        "Жильё": 0.35,
        "Транспорт": 0.10,
        "Развлечения": 0.08,
        "Здоровье": 0.07,
        "Покупки": 0.10,
    }


async def main():
    parser = argparse.ArgumentParser(description="Генератор тестовых бюджетов на последние месяцы.")
    parser.add_argument("--telegram-id", type=int, required=True, help="telegram_id пользователя")
    parser.add_argument("--months", type=int, default=6, help="на сколько полных месяцев назад создать бюджеты")
    parser.add_argument("--seed", type=int, default=42, help="seed для воспроизводимости")
    parser.add_argument("--budget-total", type=float, default=100000.0, help="общий бюджет в месяц")
    parser.add_argument("--volatility", type=float, default=0.06, help="шум бюджета по месяцам (0.06 = ±6%)")
    parser.add_argument("--wipe", action="store_true", help="удалить старые бюджеты пользователя за эти месяцы")

    args = parser.parse_args()
    rng = random.Random(args.seed)

    pool = await connect_pool()
    async with pool.acquire() as conn:
        user_id = await get_user_id(conn, args.telegram_id)
        cats = await get_expense_categories(conn, user_id)
        if not cats:
            raise RuntimeError("Нет expense-категорий. Сначала сгенерируй транзакции/категории.")

        weights = default_budget_weights()

        now = datetime.now()
        current_m = month_start(now)
        start_m = add_months(current_m, -args.months)
        months_list = [add_months(start_m, i) for i in range(args.months)]

        # при wipe удаляем бюджеты пользователя за эти месяцы
        if args.wipe:
            await conn.execute(
                "DELETE FROM budgets WHERE user_id=$1 AND month >= $2 AND month < $3",
                user_id,
                months_list[0].date(),
                add_months(months_list[-1], 1).date(),
            )

        # подготовим mapping по названию категории -> id
        name_to_id: Dict[str, int] = {name: cid for cid, name in cats}

        # вставляем бюджеты
        inserted = 0
        for m in months_list:
            total = args.budget_total * (1.0 + rng.uniform(-args.volatility, args.volatility))

            # распределяем по категориям, но только тем, которые реально есть
            # и нормируем веса по найденным категориям
            available = [(name, w) for name, w in weights.items() if name in name_to_id]
            if not available:
                # если названия не совпали — просто равномерно
                per = total / max(1, len(cats))
                for cid, _ in cats:
                    await conn.execute(
                        """
                        INSERT INTO budgets (user_id, category_id, month, limit_amount)
                        VALUES ($1, $2, $3, $4)
                        ON CONFLICT (user_id, category_id, month)
                        DO UPDATE SET limit_amount=EXCLUDED.limit_amount
                        """,
                        user_id, cid, m.date(), money(per)
                    )
                    inserted += 1
                continue

            s = sum(w for _, w in available)
            for name, w in available:
                cid = name_to_id[name]
                limit_amt = total * (w / s)

                await conn.execute(
                    """
                    INSERT INTO budgets (user_id, category_id, month, limit_amount)
                    VALUES ($1, $2, $3, $4)
                    ON CONFLICT (user_id, category_id, month)
                    DO UPDATE SET limit_amount=EXCLUDED.limit_amount
                    """,
                    user_id, cid, m.date(), money(limit_amt)
                )
                inserted += 1

        print(f"✅ Готово. Создано/обновлено бюджетов: {inserted}")
        print(f"   Период: {months_list[0].date()} .. {add_months(months_list[-1], 1).date()} (полные месяцы)")

    await pool.close()


if __name__ == "__main__":
    asyncio.run(main())