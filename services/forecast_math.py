# services/forecast_math.py
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import List, Optional, Tuple

from services.ml_forecast import linear_regression_forecast, format_ml_line


def _to_decimal(x) -> Decimal:
    if isinstance(x, Decimal):
        return x
    return Decimal(str(x))


def _round_rub(x: Decimal) -> Decimal:
    return x.quantize(Decimal("1"), rounding=ROUND_HALF_UP)


def _pct(a: Decimal, b: Decimal) -> Optional[int]:
    if b == 0:
        return None
    v = (a - b) / b * Decimal("100")
    return int(v.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _mean(values: List[Decimal]) -> Decimal:
    if not values:
        return Decimal("0")
    return sum(values) / Decimal(len(values))


def _median(values: List[Decimal]) -> Decimal:
    if not values:
        return Decimal("0")
    s = sorted(values)
    n = len(s)
    mid = n // 2
    if n % 2 == 1:
        return s[mid]
    return (s[mid - 1] + s[mid]) / Decimal("2")


def _mad(values: List[Decimal]) -> Decimal:
    if not values:
        return Decimal("0")
    med = _median(values)
    abs_dev = [abs(v - med) for v in values]
    return _median(abs_dev)


def weighted_forecast(last_months: List[Decimal]) -> Decimal:
    """
    Взвешенное среднее:
      последний месяц 0.5
      предпоследний  0.3
      третий         0.2
    """
    m = last_months[-3:]
    if not m:
        return Decimal("0")

    if len(m) == 1:
        return m[0]
    if len(m) == 2:
        w = [Decimal("0.4"), Decimal("0.6")]
        return m[0] * w[0] + m[1] * w[1]

    weights_full = [Decimal("0.2"), Decimal("0.3"), Decimal("0.5")]
    return m[0] * weights_full[0] + m[1] * weights_full[1] + m[2] * weights_full[2]


def robust_interval(history: List[Decimal], point: Decimal) -> Tuple[Decimal, Decimal]:
    """
    Устойчивый диапазон:
    - MAD -> sigma
    - ограничиваем 70%..130% от прогноза
    """
    sample = history[-6:] if len(history) >= 2 else history

    mad = _mad(sample)
    sigma = mad * Decimal("1.4826")

    if sigma == 0 and point > 0:
        sigma = point * Decimal("0.10")

    low = point - sigma
    high = point + sigma
    if low < 0:
        low = Decimal("0")

    if point > 0:
        min_low = point * Decimal("0.70")
        max_high = point * Decimal("1.30")
        if low < min_low:
            low = min_low
        if high > max_high:
            high = max_high

    return low, high


def build_warning(history: List[Decimal]) -> Optional[str]:
    """
    ⚠️ Вы тратите больше обычного: +18% к прошлому месяцу
    """
    if len(history) < 2:
        return None

    last = history[-1]
    prev = history[-2]
    trend_pct = _pct(last, prev)
    if trend_pct is None:
        return None

    base = _mean(history[-6:])
    if base == 0:
        return None

    if trend_pct >= 15 and last > base * Decimal("1.15"):
        return f"⚠️ Вы тратите больше обычного: +{trend_pct}% к прошлому месяцу"

    return None


def build_budget_note(budget_share_pct: Optional[int]) -> Optional[str]:
    """
    📌 Доля бюджета на категорию: 30%
    """
    if budget_share_pct is None:
        return None
    return f"📌 Доля бюджета на категорию: {budget_share_pct}%"


def build_advice(
    top_category_name: Optional[str],
    expense_share_pct: Optional[int],
    budget_share_pct: Optional[int],
) -> Optional[str]:
    """
    Логика:
    - если есть бюджет: сравниваем фактическую долю расходов с рекомендуемой (<=30%)
      и дополнительно учитываем долю бюджета
    - если бюджета нет: даём совет по доле расходов
    """
    if not top_category_name:
        return None
    if expense_share_pct is None:
        return None

    recommended = 30  # базовая рекомендация как в твоём примере

    if budget_share_pct is not None:
        # совет показываем, если расходы по категории "высокие"
        if expense_share_pct > recommended:
            return (
                f"💡 Совет: {top_category_name} = {expense_share_pct}% расходов "
                f"(бюджет {budget_share_pct}%) — лучше держать ≤ {recommended}%"
            )
        return None

    # без бюджета — просто по доле расходов
    if expense_share_pct > recommended:
        return f"💡 Совет: {top_category_name} = {expense_share_pct}% расходов — лучше держать ≤ {recommended}%"

    return None


def format_rub(x: Decimal) -> str:
    x = _round_rub(x)
    s = f"{int(x):,}".replace(",", " ")
    return f"{s} ₽"


def build_forecast_text(
    monthly_expenses: List[Decimal],
    top_category_name: Optional[str],
    top_category_share_pct: Optional[int],   # доля расходов
    budget_share_pct: Optional[int],         # доля бюджета (если есть)
) -> str:
    if len(monthly_expenses) < 2:
        return (
            "📈 Прогноз расходов\n\n"
            "Недостаточно данных для прогноза.\n"
            "Нужно минимум 2 полных месяца расходов."
        )

    history = [_to_decimal(x) for x in monthly_expenses]
    last = history[-1]
    prev = history[-2]

    point = weighted_forecast(history)
    low, high = robust_interval(history, point)

    trend_pct = _pct(last, prev)
    warning = build_warning(history)

    used_months = min(len(history), 6)

    # ML прогноз (Ridge)
    ml_res = linear_regression_forecast(history[-used_months:], ridge_alpha=Decimal("1"))
    ml_line = format_ml_line(ml_res)

    budget_note = build_budget_note(budget_share_pct)
    advice = build_advice(top_category_name, top_category_share_pct, budget_share_pct)

    lines = [
        f"💸 Прогноз расходов на следующий месяц: ≈ {format_rub(point)}",
        f"Диапазон: {format_rub(low)} – {format_rub(high)}",
        f"📅 Основано на данных за {used_months} мес.",
        ml_line,
    ]

    if trend_pct is not None:
        sign = "+" if trend_pct >= 0 else ""
        lines.append(f"📊 Тренд: {sign}{trend_pct}% к прошлому месяцу")
    else:
        lines.append("📊 Тренд: недостаточно данных")

    if top_category_name and top_category_share_pct is not None:
        lines.append(f"Самая затратная категория: {top_category_name} — {top_category_share_pct}%")
    else:
        lines.append("Самая затратная категория: нет данных")

    if budget_note:
        lines.append(budget_note)

    if warning:
        lines.append(warning)

    if advice:
        lines.append(advice)

    return "\n".join(lines)