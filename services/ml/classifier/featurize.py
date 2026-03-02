# services/ml/classifier/featurize.py

import re


def normalize_text(note: str) -> str:
    """
    Лёгкая нормализация текста под TF-IDF (русский текст).
    - lower
    - числа -> NUM
    - убираем мусорные символы
    - схлопываем пробелы
    """
    if not note:
        return ""

    text = note.lower()

    # заменить все числа на токен NUM
    text = re.sub(r"\d+([.,]\d+)?", " NUM ", text)

    # оставить буквы/цифры/пробелы
    text = re.sub(r"[^a-zа-я0-9\s]", " ", text, flags=re.IGNORECASE)

    # убрать лишние пробелы
    text = re.sub(r"\s+", " ", text).strip()
    return text


def build_text(note: str, amount: float) -> str:
    """
    ЕДИНЫЙ формат текста для train и predict:
      normalize_text(note) + " AMT_<rounded_amount>"

    Важно: использовать везде одинаково, чтобы vectorizer видел то, на чём обучался.
    """
    note = (note or "").strip()
    text = normalize_text(note)

    try:
        amt = float(amount) if amount is not None else 0.0
    except (TypeError, ValueError):
        amt = 0.0

    amount_token = f" AMT_{int(round(amt))} "
    full_text = f"{text}{amount_token}".strip()
    return full_text
