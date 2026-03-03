# database/db.py
# Работа с PostgreSQL через asyncpg

import os
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


db = Database()