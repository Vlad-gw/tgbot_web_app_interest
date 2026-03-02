# database/repository.py

from typing import Optional
from datetime import datetime
from database.db import db


class TransactionRepository:
    """
    Единый слой работы с транзакциями.
    Используется ботом, ML и веб-приложением.
    """

    @staticmethod
    async def get_user_id(telegram_id: int) -> int:
        return await db.execute(
            "SELECT id FROM users WHERE telegram_id = $1",
            telegram_id,
            fetchval=True
        )

    @staticmethod
    async def get_category_id(
        user_id: int,
        category_name: str,
        type_: str
    ) -> Optional[int]:
        return await db.execute(
            """
            SELECT id
            FROM categories
            WHERE user_id = $1
              AND name = $2
              AND type = $3
            """,
            user_id, category_name, type_,
            fetchval=True
        )

    @staticmethod
    async def create_category(
        user_id: int,
        category_name: str,
        type_: str
    ) -> int:
        return await db.execute(
            """
            INSERT INTO categories (user_id, name, type)
            VALUES ($1, $2, $3)
            RETURNING id
            """,
            user_id, category_name, type_,
            fetchval=True
        )

    @staticmethod
    async def add_transaction(
        *,
        user_id: int,
        category_id: int,
        amount: float,
        datetime_: datetime,
        type_: str,
        note: Optional[str],
        suggested_category_id: Optional[int] = None,
        is_category_accepted: bool = True
    ) -> None:
        await db.execute(
            """
            INSERT INTO transactions (
                user_id,
                category_id,
                suggested_category_id,
                is_category_accepted,
                amount,
                date,
                type,
                note
            )
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8)
            """,
            user_id,
            category_id,
            suggested_category_id,
            is_category_accepted,
            amount,
            datetime_,
            type_,
            note,
            execute=True
        )
