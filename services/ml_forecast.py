# services/ml_forecast.py
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import List, Optional


@dataclass
class MLForecastResult:
    predicted: Decimal
    model_name: str
    slope: Decimal
    intercept: Decimal
    r2: Optional[Decimal]


def _to_decimal(x) -> Decimal:
    if isinstance(x, Decimal):
        return x
    return Decimal(str(x))


def _round_rub(x: Decimal) -> Decimal:
    return x.quantize(Decimal("1"), rounding=ROUND_HALF_UP)


def _safe_div(a: Decimal, b: Decimal) -> Optional[Decimal]:
    if b == 0:
        return None
    return a / b


def linear_regression_forecast(
    y_values: List[Decimal],
    ridge_alpha: Decimal = Decimal("1"),
) -> MLForecastResult:

    if len(y_values) < 2:
        return MLForecastResult(
            predicted=Decimal("0"),
            model_name="LinearRegression",
            slope=Decimal("0"),
            intercept=Decimal("0"),
            r2=None,
        )

    y = [_to_decimal(v) for v in y_values]
    n = len(y)

    x = [Decimal(i) for i in range(n)]

    x_mean = sum(x) / Decimal(n)
    y_mean = sum(y) / Decimal(n)

    num = sum((x[i] - x_mean) * (y[i] - y_mean) for i in range(n))
    den = sum((x[i] - x_mean) ** 2 for i in range(n)) + _to_decimal(ridge_alpha)

    a = _safe_div(num, den)
    if a is None:
        a = Decimal("0")

    b = y_mean - a * x_mean

    y_pred_next = a * Decimal(n) + b

    ss_tot = sum((yy - y_mean) ** 2 for yy in y)
    ss_res = Decimal("0")

    for i in range(n):
        y_hat = a * x[i] + b
        ss_res += (y[i] - y_hat) ** 2

    r2 = None
    r2_val = _safe_div((ss_tot - ss_res), ss_tot) if ss_tot != 0 else None

    if r2_val is not None:
        if r2_val > 1:
            r2_val = Decimal("1")
        if r2_val < -1:
            r2_val = Decimal("-1")

        r2 = r2_val.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    return MLForecastResult(
        predicted=_round_rub(y_pred_next if y_pred_next > 0 else Decimal("0")),
        model_name="RidgeRegression",
        slope=a.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
        intercept=b.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
        r2=r2,
    )


def format_ml_line(res: MLForecastResult) -> str:

    rub = f"{int(res.predicted):,}".replace(",", " ")

    if res.r2 is None:
        return f"🤖 ML-прогноз: ≈ {rub} ₽"

    r2_percent = int(res.r2 * 100)

    if res.r2 < Decimal("0.2"):
        return f"🤖 ML-прогноз: ≈ {rub} ₽ (низкая уверенность)"

    if res.r2 < Decimal("0.5"):
        return f"🤖 ML-прогноз: ≈ {rub} ₽ (средняя точность)"

    return f"🤖 ML-прогноз: ≈ {rub} ₽ (точность модели: {r2_percent}%)"