# services/bank_import/sber_pdf.py

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pdfplumber

from services.bank_import.models import ParsedStatementOperation


OPERATION_START_RE = re.compile(
    r"^(?P<date>\d{2}\.\d{2}\.\d{4})\s+"
    r"(?P<time>\d{2}:\d{2})\s+"
    r"(?P<code>\d{6})\s+"
    r"(?P<category>.+?)\s+"
    r"(?P<amount>[+-]?\d[\d\s]*,\d{2})\s+"
    r"(?P<balance>\d[\d\s]*,\d{2})$"
)

DESCRIPTION_LINE_RE = re.compile(
    r"^(?P<date>\d{2}\.\d{2}\.\d{4})\s+(?P<desc>.+)$"
)

PERIOD_RE = re.compile(
    r"Итого по операциям с\s+(?P<from>\d{2}\.\d{2}\.\d{4})\s+по\s+(?P<to>\d{2}\.\d{2}\.\d{4})"
)

ACCOUNT_MASK_RE = re.compile(r"\*{4}\d{4}")
DOC_END_RE = re.compile(r"^Дата формирования документа\b", re.IGNORECASE)


def _normalize_spaces(text: str) -> str:
    text = text.replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\s+\n", "\n", text)
    return text.strip()


def _parse_amount(text: str) -> float:
    return float(text.replace(" ", "").replace(",", "."))


def _to_iso_date(date_str: str) -> str:
    dd, mm, yyyy = date_str.split(".")
    return f"{yyyy}-{mm}-{dd}"


def _extract_pdf_text(pdf_path: str | Path) -> str:
    chunks: list[str] = []

    with pdfplumber.open(str(pdf_path)) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            chunks.append(text)

    return "\n".join(chunks)


def _extract_period(full_text: str) -> tuple[str | None, str | None]:
    match = PERIOD_RE.search(full_text)
    if not match:
        return None, None

    return _to_iso_date(match.group("from")), _to_iso_date(match.group("to"))


def _cut_operations_block(full_text: str) -> list[str]:
    start_marker = "Расшифровка операций"
    start_idx = full_text.find(start_marker)
    if start_idx == -1:
        raise ValueError("Не найден раздел 'Расшифровка операций' в PDF выписке Сбербанка.")

    text = full_text[start_idx + len(start_marker):]

    lines = []
    for raw_line in text.splitlines():
        line = _normalize_spaces(raw_line)
        if not line:
            continue

        if DOC_END_RE.match(line):
            break

        # Убираем шапки/мусор
        skip_prefixes = (
            "ДАТА ОПЕРАЦИИ",
            "Дата обработки",
            "КАТЕГОРИЯ",
            "Описание операции",
            "СУММА В ВАЛЮТЕ СЧЁТА",
            "Сумма в валюте",
            "ОСТАТОК СРЕДСТВ",
            "В ВАЛЮТЕ СЧЁТА",
            "Продолжение на следующей странице",
            "Выписка по платёжному счёту Страница",
        )
        if any(line.startswith(prefix) for prefix in skip_prefixes):
            continue

        lines.append(line)

    return lines


def _normalize_description(description: str, category: str) -> str:
    text = _normalize_spaces(description)

    text = ACCOUNT_MASK_RE.sub("", text)
    text = re.sub(r"\.\s*Операция по счету\s*$", "", text, flags=re.IGNORECASE)
    text = re.sub(r"Операция по счету\s*$", "", text, flags=re.IGNORECASE)
    text = re.sub(r"Для проверки подлинности документа.*", "", text)
    text = re.sub(r"\s+", " ", text).strip(" .")

    if not text:
        return category

    # Нормализация переводов
    text = re.sub(r"^Перевод для\s+", "Перевод для ", text, flags=re.IGNORECASE)
    text = re.sub(r"^Перевод от\s+", "Перевод от ", text, flags=re.IGNORECASE)

    return text.strip()


def _is_internal_transfer(category: str, description: str) -> bool:
    text = f"{category} {description}".upper()
    internal_markers = [
        "KARTA-VKLAD",
        "СВОИМИ СЧЕТАМИ",
        "МЕЖДУ СВОИМИ СЧЕТАМИ",
        "ПЕРЕВОД МЕЖДУ СЧЕТАМИ",
        "СБЕРБАНК ОНЛАЙН KARTA-VKLAD",
        "SBERBANK ONL@IN KARTA-VKLAD",
    ]
    return any(marker in text for marker in internal_markers)


def _detect_tx_type(category: str, description: str, amount_raw: float) -> str:
    category_l = category.lower()
    description_l = description.lower()

    # 1. Явные правила по категории
    if "перевод с карты" in category_l:
        return "expense"

    if "перевод на карту" in category_l:
        return "income"

    # 2. Для "прочих операций" смотрим описание
    if "прочие операции" in category_l:
        if "перевод от " in description_l:
            return "income"
        if "перевод для " in description_l:
            return "expense"
        if "regular charge" in description_l:
            return "expense"
        if "подписк" in description_l:
            return "expense"
        if "оплата" in description_l:
            return "expense"
        if "покуп" in description_l:
            return "expense"

    # 3. Фоллбек по знаку
    return "income" if amount_raw > 0 else "expense"


def parse_sber_statement_pdf(pdf_path: str | Path) -> dict[str, Any]:
    full_text = _extract_pdf_text(pdf_path)
    period_from, period_to = _extract_period(full_text)
    lines = _cut_operations_block(full_text)

    operations: list[ParsedStatementOperation] = []
    skipped_internal = 0
    total_rows_found = 0

    current: dict[str, Any] | None = None

    def finalize_current() -> None:
        nonlocal current, skipped_internal, total_rows_found

        if not current:
            return

        total_rows_found += 1

        category = current["category"]
        raw_description = current["description"] or category
        normalized_description = _normalize_description(raw_description, category)

        if _is_internal_transfer(category, normalized_description):
            skipped_internal += 1
            current = None
            return

        tx_type = _detect_tx_type(category, normalized_description, current["amount_raw"])

        operations.append(
            ParsedStatementOperation(
                bank_name="sber",
                operation_date=_to_iso_date(current["date"]),
                amount=abs(current["amount_raw"]),
                currency="RUR",
                tx_type=tx_type,
                description=normalized_description,
                raw_description=raw_description,
                external_id=current["code"],
                mcc=None,
                merchant=None,
            )
        )

        current = None

    i = 0
    while i < len(lines):
        line = lines[i]

        start_match = OPERATION_START_RE.match(line)
        if start_match:
            finalize_current()

            current = {
                "date": start_match.group("date"),
                "time": start_match.group("time"),
                "code": start_match.group("code"),
                "category": _normalize_spaces(start_match.group("category")),
                "amount_raw": _parse_amount(start_match.group("amount")),
                "balance": _parse_amount(start_match.group("balance")),
                "description": "",
            }

            # Собираем следующие строки описания до начала новой операции
            j = i + 1
            description_parts: list[str] = []

            while j < len(lines):
                next_line = lines[j]

                if OPERATION_START_RE.match(next_line):
                    break

                desc_match = DESCRIPTION_LINE_RE.match(next_line)
                if desc_match:
                    desc_text = desc_match.group("desc").strip()
                    if desc_text:
                        description_parts.append(desc_text)
                else:
                    description_parts.append(next_line)

                j += 1

            current["description"] = _normalize_spaces(" ".join(description_parts))
            i = j
            continue

        i += 1

    finalize_current()

    return {
        "bank_name": "sber",
        "period_from": period_from,
        "period_to": period_to,
        "operations": [op.to_dict() for op in operations],
        "skipped_hold": 0,
        "skipped_internal": skipped_internal,
        "total_rows_found": total_rows_found,
        "ready_to_import": len(operations),
    }