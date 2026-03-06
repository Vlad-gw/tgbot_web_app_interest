# services/bank_import/preview.py

from __future__ import annotations


def format_statement_preview(parsed: dict) -> str:
    operations = parsed.get("operations", [])

    income_count = sum(1 for op in operations if op["tx_type"] == "income")
    expense_count = sum(1 for op in operations if op["tx_type"] == "expense")

    total_income = sum(op["amount"] for op in operations if op["tx_type"] == "income")
    total_expense = sum(op["amount"] for op in operations if op["tx_type"] == "expense")

    total_rows_found = parsed.get("total_rows_found", len(operations))
    skipped_hold = parsed.get("skipped_hold", 0)
    skipped_internal = parsed.get("skipped_internal", 0)
    ready_to_import = parsed.get("ready_to_import", len(operations))

    bank_label = parsed.get("bank_name", "").upper()

    lines = [
        "📄 <b>Превью выписки</b>",
        f"<b>Банк:</b> {bank_label}",
        f"<b>Период:</b> {parsed.get('period_from') or '—'} — {parsed.get('period_to') or '—'}",
        "",
        f"<b>Всего найдено строк операций:</b> {total_rows_found}",
        f"<b>Готово к импорту:</b> {ready_to_import}",
        f"<b>Доходов:</b> {income_count} на сумму {total_income:.2f} ₽",
        f"<b>Расходов:</b> {expense_count} на сумму {total_expense:.2f} ₽",
        f"<b>Пропущено HOLD:</b> {skipped_hold}",
        f"<b>Пропущено внутренних переводов:</b> {skipped_internal}",
        "",
        "<b>Первые операции:</b>",
    ]

    preview_ops = operations[:10]
    if not preview_ops:
        lines.append("Операции не найдены.")
    else:
        for op in preview_ops:
            sign = "➕" if op["tx_type"] == "income" else "➖"
            lines.append(
                f"{sign} {op['operation_date']} | {op['amount']:.2f} ₽ | "
                f"{op['description'][:80]}"
            )

    return "\n".join(lines)