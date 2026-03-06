# services/bank_import/alfa_pdf.py

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pdfplumber

from services.bank_import.models import ParsedStatementOperation


DATE_LINE_RE = re.compile(
    r"^(?P<date>\d{2}\.\d{2}\.\d{4})\s+(?P<code>[A-Z0-9_]+)\s+(?P<rest>.+)$"
)

AMOUNT_RE = re.compile(
    r"(?P<amount>[+-]?\d[\d ]*,\d{2})\s+RUR$"
)

PERIOD_RE = re.compile(
    r"За период с\s+(\d{2}\.\d{2}\.\d{4})\s+по\s+(\d{2}\.\d{2}\.\d{4})"
)

MCC_RE = re.compile(r"MCC(\d{4})", re.IGNORECASE)

CARD_MERCHANT_RE = re.compile(
    r"место совершения операции:\s*(.+?)\s*MCC\d{4}",
    re.IGNORECASE | re.DOTALL,
)

RAW_CARD_PATTERN_RE = re.compile(
    r"^\d+\\RU\\[A-ZА-ЯЁ \-]+\\(.+)$",
    re.IGNORECASE
)


def _normalize_spaces(text: str) -> str:
    text = text.replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\s+\n", "\n", text)
    return text.strip()


def _parse_amount(amount_str: str) -> float:
    cleaned = amount_str.replace(" ", "").replace(",", ".")
    return float(cleaned)


def _to_iso_date(date_str: str) -> str:
    dd, mm, yyyy = date_str.split(".")
    return f"{yyyy}-{mm}-{dd}"


def _extract_pdf_text(pdf_path: str | Path) -> str:
    chunks: list[str] = []

    with pdfplumber.open(str(pdf_path)) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            chunks.append(text)

    return _normalize_spaces("\n".join(chunks))


def _cut_to_operations_block(full_text: str) -> str:
    marker = "Операции по счету"
    idx = full_text.find(marker)
    if idx == -1:
        raise ValueError("Не найден раздел 'Операции по счету' в PDF выписке Альфа-Банка.")

    text = full_text[idx + len(marker):]

    garbage_patterns = [
        r"Т\.Т\. Трофимова.*?Страница \d+ из \d+",
        r"Уполномоченное лицо",
        r"\(подпись сотрудника АО «АЛЬФА-БАНК»\)",
        r"\(Ф\.И\.О\. сотрудника АО «АЛЬФА-БАНК»\)",
        r"Дата проводки Код операции Описание Сумма\s*в валюте счета",
        r"Страница \d+ из \d+",
    ]

    for pattern in garbage_patterns:
        text = re.sub(pattern, "", text, flags=re.DOTALL)

    return _normalize_spaces(text)


def _extract_period(full_text: str) -> tuple[str | None, str | None]:
    m = PERIOD_RE.search(full_text)
    if not m:
        return None, None

    return _to_iso_date(m.group(1)), _to_iso_date(m.group(2))


def _extract_amount_from_line(line: str) -> tuple[float | None, str]:
    m = AMOUNT_RE.search(line)
    if not m:
        return None, line

    amount = _parse_amount(m.group("amount"))
    rest = line[:m.start()].strip()
    return amount, rest


def _titleize_merchant(text: str) -> str:
    text = text.strip()
    text = re.sub(r"\s+", " ", text)

    keep_upper = {
        "RU", "MCC", "YANDEX", "WB", "OZON", "DNS", "KFC", "SBER", "SBP",
        "VK", "PS", "STEAM", "APPLE", "GOOGLE", "MTS"
    }

    parts = []
    for word in text.split():
        cleaned = re.sub(r"[^\w\-&/+.]", "", word, flags=re.UNICODE)
        if not cleaned:
            continue
        if cleaned.upper() in keep_upper:
            parts.append(cleaned.upper())
        elif cleaned.isdigit():
            parts.append(cleaned)
        else:
            parts.append(cleaned.capitalize())

    return " ".join(parts).strip()


def _cleanup_card_tail(text: str) -> str:
    text = text.replace("\\", " ")
    text = re.sub(r"\bRU\b", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"\bMOSKVA\b", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"\bSANKT PETERBU\b", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"\bSANKT-PETERBU\b", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"\bMCC\d{4}\b", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"\b\d{4}\b", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _normalize_description(raw_description: str) -> str:
    text = _normalize_spaces(raw_description)

    # 1. Попытка вытащить merchant из подробного текста карточной операции
    merchant_match = CARD_MERCHANT_RE.search(text)
    if merchant_match:
        merchant = merchant_match.group(1)
        merchant = _cleanup_card_tail(merchant)
        merchant = _titleize_merchant(merchant)
        if merchant:
            return merchant

    # 2. Попытка вытащить merchant из краткой сырой строки вида 82083942\RU\MOSKVA\YANDEX 5815 PLUS
    raw_card_match = RAW_CARD_PATTERN_RE.match(text)
    if raw_card_match:
        merchant = raw_card_match.group(1)
        merchant = _cleanup_card_tail(merchant)
        merchant = _titleize_merchant(merchant)
        if merchant:
            return merchant

    # 3. Упростить переводы по СБП
    if "через Систему быстрых платежей" in text:
        if " от +" in text:
            phone_match = re.search(r"от\s+(\+\d+)", text)
            phone = phone_match.group(1) if phone_match else ""
            return f"Перевод по СБП от {phone}".strip()
        if " на +" in text:
            phone_match = re.search(r"на\s+(\+\d+)", text)
            phone = phone_match.group(1) if phone_match else ""
            return f"Перевод по СБП на {phone}".strip()
        return "Перевод по СБП"

    # 4. Обычная чистка
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _extract_merchant_and_mcc(raw_description: str) -> tuple[str | None, str | None]:
    mcc_match = MCC_RE.search(raw_description)
    mcc = mcc_match.group(1) if mcc_match else None

    normalized = _normalize_description(raw_description)
    merchant = normalized if normalized != raw_description else None

    return merchant, mcc


def parse_alfa_statement_pdf(pdf_path: str | Path) -> dict[str, Any]:
    full_text = _extract_pdf_text(pdf_path)
    ops_text = _cut_to_operations_block(full_text)
    period_from, period_to = _extract_period(full_text)

    lines = [line.strip() for line in ops_text.splitlines() if line.strip()]

    operations: list[ParsedStatementOperation] = []
    skipped_hold = 0
    skipped_internal = 0
    total_rows_found = 0

    current: dict[str, Any] | None = None

    def finalize_current() -> None:
        nonlocal current, skipped_hold, skipped_internal, total_rows_found

        if not current:
            return

        total_rows_found += 1

        date_str: str = current["date"]
        code: str = current["code"]
        raw_description: str = _normalize_spaces(current["description"])
        amount: float = current["amount"]

        if raw_description.upper().startswith("HOLD "):
            skipped_hold += 1
            current = None
            return

        if "Внутрибанковский перевод между счетами" in raw_description:
            skipped_internal += 1
            current = None
            return

        tx_type = "income" if amount > 0 else "expense"
        merchant, mcc = _extract_merchant_and_mcc(raw_description)
        description = merchant or raw_description

        operations.append(
            ParsedStatementOperation(
                bank_name="alfa",
                operation_date=_to_iso_date(date_str),
                amount=abs(amount),
                currency="RUR",
                tx_type=tx_type,
                description=description,
                raw_description=raw_description,
                external_id=code,
                mcc=mcc,
                merchant=merchant,
            )
        )
        current = None

    for line in lines:
        if line.startswith("HOLD "):
            skipped_hold += 1
            continue

        m = DATE_LINE_RE.match(line)
        if m:
            finalize_current()

            date_str = m.group("date")
            code = m.group("code")
            rest = m.group("rest").strip()

            amount, desc_without_amount = _extract_amount_from_line(rest)

            if amount is None:
                current = {
                    "date": date_str,
                    "code": code,
                    "description": rest,
                    "amount": 0.0,
                }
            else:
                current = {
                    "date": date_str,
                    "code": code,
                    "description": desc_without_amount,
                    "amount": amount,
                }
            continue

        if current:
            appended_amount, cleaned_line = _extract_amount_from_line(line)
            if appended_amount is not None and current["amount"] == 0.0:
                current["amount"] = appended_amount
                if cleaned_line:
                    current["description"] += " " + cleaned_line
            else:
                current["description"] += " " + line

    finalize_current()

    return {
        "bank_name": "alfa",
        "period_from": period_from,
        "period_to": period_to,
        "operations": [op.to_dict() for op in operations],
        "skipped_hold": skipped_hold,
        "skipped_internal": skipped_internal,
        "total_rows_found": total_rows_found,
        "ready_to_import": len(operations),
    }