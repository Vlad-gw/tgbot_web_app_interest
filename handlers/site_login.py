# handlers/site_login.py

import os
import secrets
import hashlib
from datetime import datetime, timedelta

from aiogram import Router, F
from aiogram.types import Message

from database.db import db

router = Router()


def _gen_code() -> str:
    return f"{secrets.randbelow(10**8):08d}"


def _hash_code(code: str) -> str:
    pepper = os.getenv("AUTH_CODE_PEPPER", "")
    return hashlib.sha256((pepper + code).encode("utf-8")).hexdigest()


@router.message(F.text == "🔑 Войти на сайт")
async def login_to_site(message: Message):
    tg_id = message.from_user.id

    pepper = os.getenv("AUTH_CODE_PEPPER", "")
    if not pepper:
        await message.answer(
            "❌ AUTH_CODE_PEPPER не задан.\n"
            "Добавь в .env:\n"
            "AUTH_CODE_PEPPER=любая_длинная_строка\n"
            "SITE_URL=http://127.0.0.1:8000\n"
            "и перезапусти бота."
        )
        return

    code = _gen_code()
    code_hash = _hash_code(code)

    now = datetime.utcnow()
    expires_at = now + timedelta(minutes=2)

    # Закрываем старые активные коды этого пользователя
    await db.execute(
        """
        UPDATE auth_codes
        SET used_at = NOW()
        WHERE telegram_id = $1
          AND used_at IS NULL
          AND expires_at > NOW()
        """,
        tg_id,
        execute=True
    )

    # Создаём новый код
    await db.execute(
        """
        INSERT INTO auth_codes (telegram_id, code_hash, expires_at)
        VALUES ($1, $2, $3)
        """,
        tg_id,
        code_hash,
        expires_at,
        execute=True
    )

    site_url = os.getenv("SITE_URL", "http://127.0.0.1:8000").rstrip("/")
    await message.answer(
        "🔐 <b>Код для входа на сайт</b>\n\n"
        f"<code>{code}</code>\n\n"
        "⏳ Действует 2 минуты и только один раз.\n"
        f"Открой: {site_url}/finance/login/ и введи код."
    )