# database/repository.py

from typing import Optional
from datetime import datetime, date
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
    def _parse_iso_date(value):
        if value is None:
            return None
        if isinstance(value, date):
            return value
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, str):
            return datetime.strptime(value, "%Y-%m-%d").date()
        raise ValueError(f"Неподдерживаемый формат даты: {value!r}")

    @staticmethod
    def _parse_transaction_datetime(value):
        if value is None:
            return None
        if isinstance(value, datetime):
            return value
        if isinstance(value, date):
            return value
        if isinstance(value, str):
            # для импорта выписки у нас сейчас YYYY-MM-DD
            return datetime.strptime(value, "%Y-%m-%d").date()
        return value

    @staticmethod
    async def add_transaction(
        *,
        user_id: int,
        category_id: int,
        amount: float,
        datetime_,
        type_: str,
        note: Optional[str],
        suggested_category_id: Optional[int] = None,
        is_category_accepted: bool = True,
        source: str = "manual",
        source_bank: Optional[str] = None,
        source_external_id: Optional[str] = None,
        source_hash: Optional[str] = None,
        import_batch_id: Optional[int] = None,
        raw_description: Optional[str] = None,
    ) -> None:
        date_value = TransactionRepository._parse_transaction_datetime(datetime_)

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
                note,
                source,
                source_bank,
                source_external_id,
                source_hash,
                import_batch_id,
                raw_description
            )
            VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14)
            """,
            user_id,
            category_id,
            suggested_category_id,
            is_category_accepted,
            amount,
            date_value,
            type_,
            note,
            source,
            source_bank,
            source_external_id,
            source_hash,
            import_batch_id,
            raw_description,
            execute=True
        )

    @staticmethod
    async def create_statement_import(
        *,
        user_id: int,
        bank_name: str,
        file_name: str,
        file_type: str,
        period_from: Optional[str],
        period_to: Optional[str],
        total_found: int,
    ) -> int:
        period_from_value = TransactionRepository._parse_iso_date(period_from)
        period_to_value = TransactionRepository._parse_iso_date(period_to)

        return await db.execute(
            """
            INSERT INTO statement_imports (
                user_id,
                bank_name,
                file_name,
                file_type,
                period_from,
                period_to,
                total_found
            )
            VALUES ($1,$2,$3,$4,$5,$6,$7)
            RETURNING id
            """,
            user_id,
            bank_name,
            file_name,
            file_type,
            period_from_value,
            period_to_value,
            total_found,
            fetchval=True,
        )

    @staticmethod
    async def finish_statement_import(
        *,
        import_id: int,
        total_imported: int,
        total_duplicates: int,
        total_skipped: int,
    ) -> None:
        await db.execute(
            """
            UPDATE statement_imports
            SET total_imported = $2,
                total_duplicates = $3,
                total_skipped = $4
            WHERE id = $1
            """,
            import_id,
            total_imported,
            total_duplicates,
            total_skipped,
            execute=True,
        )

    @staticmethod
    async def transaction_exists_by_external_id(
        *,
        user_id: int,
        source_bank: str,
        source_external_id: str,
    ) -> bool:
        row = await db.execute(
            """
            SELECT 1
            FROM transactions
            WHERE user_id = $1
              AND source_bank = $2
              AND source_external_id = $3
            LIMIT 1
            """,
            user_id,
            source_bank,
            source_external_id,
            fetchval=True,
        )
        return bool(row)

    @staticmethod
    async def transaction_exists_by_hash(
        *,
        user_id: int,
        source_hash: str,
    ) -> bool:
        row = await db.execute(
            """
            SELECT 1
            FROM transactions
            WHERE user_id = $1
              AND source_hash = $2
            LIMIT 1
            """,
            user_id,
            source_hash,
            fetchval=True,
        )
        return bool(row)