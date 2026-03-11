# database/db.py
# Работа с PostgreSQL через asyncpg

import os
from datetime import date
import asyncpg
from dotenv import load_dotenv

load_dotenv()

DB_HOST = os.getenv("DB_HOST")
DB_PORT = int(os.getenv("DB_PORT", 5432))
DB_NAME = os.getenv("DB_NAME")
DB_USER = os.getenv("DB_USER")
DB_PASS = os.getenv("DB_PASS")


def _check_db_env() -> None:
    missing = []
    for k, v in [
        ("DB_HOST", DB_HOST),
        ("DB_NAME", DB_NAME),
        ("DB_USER", DB_USER),
        ("DB_PASS", DB_PASS),
    ]:
        if not v:
            missing.append(k)
    if missing:
        raise RuntimeError(f"❌ Не заданы переменные в .env: {', '.join(missing)}")


class Database:
    def __init__(self):
        self.pool: asyncpg.Pool | None = None

    async def connect(self):
        _check_db_env()
        if self.pool is None:
            self.pool = await asyncpg.create_pool(
                host=DB_HOST,
                port=DB_PORT,
                user=DB_USER,
                password=DB_PASS,
                database=DB_NAME,
            )

    async def disconnect(self):
        if self.pool is not None:
            await self.pool.close()
            self.pool = None

    async def _ensure_connected(self):
        if self.pool is None:
            await self.connect()

    async def execute(
        self,
        query: str,
        *args,
        fetch: bool = False,
        fetchval: bool = False,
        fetchrow: bool = False,
        execute: bool = False,
    ):
        await self._ensure_connected()

        async with self.pool.acquire() as connection:
            if fetch:
                return await connection.fetch(query, *args)
            if fetchval:
                return await connection.fetchval(query, *args)
            if fetchrow:
                return await connection.fetchrow(query, *args)
            if execute:
                return await connection.execute(query, *args)

        raise ValueError("Не указан режим выполнения запроса")

    # =========================================================
    # USERS
    # =========================================================

    async def get_user_by_telegram_id(self, telegram_id: int):
        query = """
            SELECT *
            FROM users
            WHERE telegram_id = $1
        """
        return await self.execute(query, telegram_id, fetchrow=True)

    async def get_user_by_id(self, user_id: int):
        query = """
            SELECT *
            FROM users
            WHERE id = $1
        """
        return await self.execute(query, user_id, fetchrow=True)

    async def create_user(
        self,
        telegram_id: int,
        username: str | None = None,
        first_name: str | None = None,
    ):
        query = """
            INSERT INTO users (telegram_id, username, first_name)
            VALUES ($1, $2, $3)
            ON CONFLICT (telegram_id) DO UPDATE
            SET username = EXCLUDED.username,
                first_name = EXCLUDED.first_name
            RETURNING *
        """
        return await self.execute(
            query,
            telegram_id,
            username,
            first_name,
            fetchrow=True,
        )

    async def get_or_create_user(
        self,
        telegram_id: int,
        username: str | None = None,
        first_name: str | None = None,
    ):
        user = await self.get_user_by_telegram_id(telegram_id)
        if user:
            return user
        return await self.create_user(telegram_id, username, first_name)

    # =========================================================
    # REMINDERS
    # =========================================================

    async def ensure_reminder(self, user_id: int):
        query = """
            INSERT INTO reminders (
                user_id,
                type,
                cron,
                is_active,
                enabled,
                remind_time
            )
            VALUES (
                $1,
                'daily_transaction_reminder',
                '0 20 * * *',
                TRUE,
                TRUE,
                '20:00:00'
            )
            ON CONFLICT (user_id) DO NOTHING
            RETURNING *
        """
        reminder = await self.execute(query, user_id, fetchrow=True)
        if reminder:
            return reminder

        return await self.get_reminder_settings(user_id)

    async def get_reminder_settings(self, user_id: int):
        await self.ensure_reminder_if_needed(user_id)

        query = """
            SELECT
                id,
                user_id,
                type,
                cron,
                is_active,
                enabled,
                remind_time,
                last_sent_date,
                created_at,
                updated_at
            FROM reminders
            WHERE user_id = $1
        """
        return await self.execute(query, user_id, fetchrow=True)

    async def ensure_reminder_if_needed(self, user_id: int):
        query = """
            SELECT id
            FROM reminders
            WHERE user_id = $1
        """
        reminder = await self.execute(query, user_id, fetchrow=True)
        if reminder:
            return reminder
        return await self.ensure_reminder(user_id)

    async def set_reminder_enabled(self, user_id: int, enabled: bool):
        await self.ensure_reminder_if_needed(user_id)

        query = """
            UPDATE reminders
            SET enabled = $2,
                is_active = $2,
                updated_at = NOW()
            WHERE user_id = $1
            RETURNING *
        """
        return await self.execute(query, user_id, enabled, fetchrow=True)

    async def set_reminder_time(self, user_id: int, remind_time):
        await self.ensure_reminder_if_needed(user_id)

        query = """
            UPDATE reminders
            SET remind_time = $2,
                updated_at = NOW()
            WHERE user_id = $1
            RETURNING *
        """
        return await self.execute(query, user_id, remind_time, fetchrow=True)

    async def mark_reminder_sent(self, user_id: int, sent_date: date):
        await self.ensure_reminder_if_needed(user_id)

        query = """
            UPDATE reminders
            SET last_sent_date = $2,
                updated_at = NOW()
            WHERE user_id = $1
            RETURNING *
        """
        return await self.execute(query, user_id, sent_date, fetchrow=True)

    async def reset_reminder_sent_date(self, user_id: int):
        await self.ensure_reminder_if_needed(user_id)

        query = """
            UPDATE reminders
            SET last_sent_date = NULL,
                updated_at = NOW()
            WHERE user_id = $1
            RETURNING *
        """
        return await self.execute(query, user_id, fetchrow=True)

    async def get_users_with_active_reminders(self):
        query = """
            SELECT
                r.user_id,
                r.enabled,
                r.remind_time,
                r.last_sent_date,
                u.telegram_id,
                u.username,
                u.first_name
            FROM reminders r
            JOIN users u ON u.id = r.user_id
            WHERE r.enabled = TRUE
        """
        return await self.execute(query, fetch=True)

    async def has_transactions_for_date(self, user_id: int, check_date: date) -> bool:
        query = """
            SELECT EXISTS (
                SELECT 1
                FROM transactions
                WHERE user_id = $1
                  AND DATE(date) = $2
            )
        """
        result = await self.execute(query, user_id, check_date, fetchval=True)
        return bool(result)

    async def count_transactions_for_date(self, user_id: int, check_date: date) -> int:
        query = """
            SELECT COUNT(*)
            FROM transactions
            WHERE user_id = $1
              AND DATE(date) = $2
        """
        result = await self.execute(query, user_id, check_date, fetchval=True)
        return int(result or 0)

    # =========================================================
    # TRANSACTIONS
    # =========================================================

    async def get_transactions_for_date(self, user_id: int, check_date: date):
        query = """
            SELECT *
            FROM transactions
            WHERE user_id = $1
              AND DATE(date) = $2
            ORDER BY date DESC, id DESC
        """
        return await self.execute(query, user_id, check_date, fetch=True)

    async def get_transactions_between_dates(self, user_id: int, date_from, date_to):
        query = """
            SELECT *
            FROM transactions
            WHERE user_id = $1
              AND DATE(date) BETWEEN $2 AND $3
            ORDER BY date DESC, id DESC
        """
        return await self.execute(query, user_id, date_from, date_to, fetch=True)

    async def get_today_transactions(self, user_id: int):
        query = """
            SELECT *
            FROM transactions
            WHERE user_id = $1
              AND DATE(date) = CURRENT_DATE
            ORDER BY date DESC, id DESC
        """
        return await self.execute(query, user_id, fetch=True)


db = Database()