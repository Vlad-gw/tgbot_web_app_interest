from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, date, time, timedelta
from decimal import Decimal, InvalidOperation
from typing import Optional


@dataclass
class ParsedQuickTransaction:
    tx_type: str                  # "income" | "expense"
    amount: Decimal
    note: str
    tx_date: date
    tx_time: time
    time_provided: bool
    raw_text: str


class QuickParseError(ValueError):
    pass


_DATE_WORDS = {"сегодня", "вчера", "позавчера"}
_TIME_RE = re.compile(r"^(?P<hour>\d{1,2}):(?P<minute>\d{2})$")
_DATE_RE = re.compile(r"^(?P<day>\d{2})\.(?P<month>\d{2})\.(?P<year>\d{4})$")
_AMOUNT_RE = re.compile(r"^(?P<sign>[+-])\s*(?P<amount>\d+(?:[.,]\d{1,2})?)\s*(?P<tail>.*)$")


def parse_quick_transaction(text: str, now: Optional[datetime] = None) -> ParsedQuickTransaction:
    """
    Поддерживаемые форматы:
    +100000 зарплата
    +100000 зарплата вчера
    +100000 зарплата вчера 21:21
    +100000 зарплата 03.03.2026
    +100000 зарплата 03.03.2026 21:21
    -500 бензин сегодня
    -500 бензин сегодня 08:30
    -500 бензин 03.03.2026 19:15

    Правила:
    - '+' = income
    - '-' = expense
    - если дата не указана -> сегодня
    - если время не указано -> 00:00
    - дата и время ищутся только в конце строки
    """

    if now is None:
        now = datetime.now()

    if text is None:
        raise QuickParseError("Пустое сообщение.")

    raw_text = text
    text = " ".join(text.strip().split())

    if not text:
        raise QuickParseError("Пустое сообщение.")

    match = _AMOUNT_RE.match(text)
    if not match:
        raise QuickParseError(
            "Неверный формат. Пример: +100000 зарплата вчера 21:21"
        )

    sign = match.group("sign")
    amount_str = match.group("amount")
    tail = (match.group("tail") or "").strip()

    tx_type = "income" if sign == "+" else "expense"

    try:
        amount = Decimal(amount_str.replace(",", "."))
    except InvalidOperation:
        raise QuickParseError("Не удалось распознать сумму.")

    if amount <= 0:
        raise QuickParseError("Сумма должна быть больше нуля.")

    tokens = tail.split() if tail else []

    parsed_time = time(0, 0)
    time_provided = False
    parsed_date = now.date()

    # 1. Пробуем время в самом конце
    if tokens:
        maybe_time = tokens[-1].lower()
        if _looks_like_time(maybe_time):
            parsed_time = _parse_time_token(maybe_time)
            time_provided = True
            tokens.pop()

    # 2. Пробуем дату перед временем или в конце
    if tokens:
        maybe_date = tokens[-1].lower()
        if maybe_date in _DATE_WORDS or _looks_like_date(maybe_date):
            parsed_date = _parse_date_token(maybe_date, now.date())
            tokens.pop()

    note = " ".join(tokens).strip()

    if not note:
        raise QuickParseError(
            "Не удалось распознать описание операции. "
            "Пример: -500 бензин сегодня"
        )

    return ParsedQuickTransaction(
        tx_type=tx_type,
        amount=amount,
        note=note,
        tx_date=parsed_date,
        tx_time=parsed_time,
        time_provided=time_provided,
        raw_text=raw_text,
    )


def combine_to_datetime(parsed: ParsedQuickTransaction) -> datetime:
    return datetime.combine(parsed.tx_date, parsed.tx_time)


def _looks_like_time(value: str) -> bool:
    return bool(_TIME_RE.match(value))


def _parse_time_token(value: str) -> time:
    match = _TIME_RE.match(value)
    if not match:
        raise QuickParseError(f"Неверный формат времени: {value}")

    hour = int(match.group("hour"))
    minute = int(match.group("minute"))

    if not (0 <= hour <= 23):
        raise QuickParseError(f"Часы должны быть от 0 до 23: {value}")
    if not (0 <= minute <= 59):
        raise QuickParseError(f"Минуты должны быть от 0 до 59: {value}")

    return time(hour, minute)


def _looks_like_date(value: str) -> bool:
    return bool(_DATE_RE.match(value))


def _parse_date_token(value: str, today: date) -> date:
    value = value.lower()

    if value == "сегодня":
        return today
    if value == "вчера":
        return today - timedelta(days=1)
    if value == "позавчера":
        return today - timedelta(days=2)

    match = _DATE_RE.match(value)
    if not match:
        raise QuickParseError(f"Неверный формат даты: {value}")

    day = int(match.group("day"))
    month = int(match.group("month"))
    year = int(match.group("year"))

    try:
        return date(year, month, day)
    except ValueError:
        raise QuickParseError(f"Некорректная дата: {value}")