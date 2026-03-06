from __future__ import annotations


def resolve_income_category(note: str) -> str:
    text = (note or "").strip().lower()

    if not text:
        return "Прочие доходы"

    salary_keywords = {
        "зарплата", "зп", "аванс", "оклад", "зарп", "salary"
    }
    bonus_keywords = {
        "премия", "бонус", "bonus"
    }
    cashback_keywords = {
        "кэшбэк", "кешбэк", "cashback"
    }
    gift_keywords = {
        "подарок", "дар", "gift"
    }
    interest_keywords = {
        "проценты", "вклад", "депозит", "interest"
    }

    words = set(text.split())

    if words & salary_keywords:
        return "Зарплата"
    if words & bonus_keywords:
        return "Премия"
    if words & cashback_keywords:
        return "Кэшбэк"
    if words & gift_keywords:
        return "Подарок"
    if words & interest_keywords:
        return "Проценты"

    return "Прочие доходы"