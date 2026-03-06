# services/bank_import/importer.py

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from database.repository import TransactionRepository
from services.bank_import.alfa_pdf import parse_alfa_statement_pdf
from services.bank_import.models import ParsedStatementOperation
from services.bank_import.sber_pdf import parse_sber_statement_pdf
from services.income_category_resolver import resolve_income_category

try:
    from services.ml.classifier.predict import predict_category
except Exception:
    predict_category = None


MCC_CATEGORY_MAP = {
    "5411": "Продукты",
    "5812": "Кафе и рестораны",
    "5814": "Кафе и рестораны",
    "4131": "Транспорт",
    "3990": "Подписки",
    "7221": "Красота",
}


def build_source_hash(user_id: int, op: ParsedStatementOperation) -> str:
    base = "|".join(
        [
            str(user_id),
            op.bank_name,
            op.operation_date,
            f"{op.amount:.2f}",
            (op.external_id or "").strip(),
            op.raw_description.strip().lower(),
        ]
    )
    return hashlib.sha256(base.encode("utf-8")).hexdigest()


def parse_statement_file(bank_name: str, file_path: str | Path) -> dict[str, Any]:
    bank_name = bank_name.lower().strip()

    if bank_name == "alfa":
        return parse_alfa_statement_pdf(file_path)

    if bank_name == "sber":
        return parse_sber_statement_pdf(file_path)

    raise ValueError(f"Неизвестный банк: {bank_name}")


async def _resolve_category_for_import(
    *,
    user_id: int,
    tx_type: str,
    description: str,
    amount: float,
    mcc: str | None,
) -> tuple[int, int | None, bool]:
    """
    Возвращает:
    category_id, suggested_category_id, is_category_accepted
    """
    if tx_type == "income":
        category_name = resolve_income_category(description)

        category_id = await TransactionRepository.get_category_id(
            user_id=user_id,
            category_name=category_name,
            type_="income",
        )
        if not category_id:
            category_id = await TransactionRepository.create_category(
                user_id=user_id,
                category_name=category_name,
                type_="income",
            )

        return category_id, None, True

    category_name = None
    suggested_category_id = None
    is_category_accepted = False

    if mcc and mcc in MCC_CATEGORY_MAP:
        category_name = MCC_CATEGORY_MAP[mcc]

    if not category_name and predict_category:
        try:
            predicted_name, conf, _ = predict_category(description, float(amount), top_k=3)
            if predicted_name and conf >= 0.35:
                category_name = predicted_name
        except Exception:
            category_name = None

    if not category_name:
        category_name = "Прочее"

    category_id = await TransactionRepository.get_category_id(
        user_id=user_id,
        category_name=category_name,
        type_="expense",
    )
    if not category_id:
        category_id = await TransactionRepository.create_category(
            user_id=user_id,
            category_name=category_name,
            type_="expense",
        )

    suggested_category_id = category_id
    is_category_accepted = category_name != "Прочее"

    return category_id, suggested_category_id, is_category_accepted


async def import_parsed_operations(
    *,
    user_id: int,
    file_name: str,
    file_type: str,
    parsed: dict,
) -> dict[str, Any]:
    bank_name = parsed["bank_name"]
    operations = [ParsedStatementOperation.from_dict(x) for x in parsed.get("operations", [])]

    batch_id = await TransactionRepository.create_statement_import(
        user_id=user_id,
        bank_name=bank_name,
        file_name=file_name,
        file_type=file_type,
        period_from=parsed.get("period_from"),
        period_to=parsed.get("period_to"),
        total_found=len(operations),
    )

    imported_count = 0
    duplicate_count = 0
    skipped_count = parsed.get("skipped_hold", 0) + parsed.get("skipped_internal", 0)

    for op in operations:
        source_hash = build_source_hash(user_id, op)

        duplicate = False

        if op.external_id:
            duplicate = await TransactionRepository.transaction_exists_by_external_id(
                user_id=user_id,
                source_bank=bank_name,
                source_external_id=op.external_id,
            )

        if not duplicate:
            duplicate = await TransactionRepository.transaction_exists_by_hash(
                user_id=user_id,
                source_hash=source_hash,
            )

        if duplicate:
            duplicate_count += 1
            continue

        category_id, suggested_category_id, is_category_accepted = await _resolve_category_for_import(
            user_id=user_id,
            tx_type=op.tx_type,
            description=op.description,
            amount=op.amount,
            mcc=op.mcc,
        )

        await TransactionRepository.add_transaction(
            user_id=user_id,
            category_id=category_id,
            amount=op.amount,
            datetime_=op.operation_date,
            type_=op.tx_type,
            note=op.description,
            suggested_category_id=suggested_category_id,
            is_category_accepted=is_category_accepted,
            source="statement_import",
            source_bank=bank_name,
            source_external_id=op.external_id,
            source_hash=source_hash,
            import_batch_id=batch_id,
            raw_description=op.raw_description,
        )

        imported_count += 1

    await TransactionRepository.finish_statement_import(
        import_id=batch_id,
        total_imported=imported_count,
        total_duplicates=duplicate_count,
        total_skipped=skipped_count,
    )

    return {
        "batch_id": batch_id,
        "total_rows_found": parsed.get("total_rows_found", len(operations)),
        "ready_to_import": len(operations),
        "total_imported": imported_count,
        "total_duplicates": duplicate_count,
        "total_skipped": skipped_count,
    }