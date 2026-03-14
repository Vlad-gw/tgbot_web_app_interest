from __future__ import annotations

import hashlib
import hmac
import json
import os
from calendar import monthrange
from datetime import date, datetime, time as dtime
from decimal import Decimal, InvalidOperation
from urllib.parse import parse_qsl

from django.db import IntegrityError
from django.db.models import Q, Sum
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.request import Request
from rest_framework.response import Response

from .auth import generate_api_key, get_user_from_request
from .models import Budget, Category, Transaction, User
from .serializers import BudgetSerializer, CategorySerializer, TransactionSerializer


@api_view(["GET"])
def health(_request: Request) -> Response:
    return Response({"ok": True})


def _parse_date(s: str):
    return datetime.strptime(s, "%Y-%m-%d").date()


def _parse_month_value(value: str | None) -> date:
    if not value:
        today = datetime.now().date()
        return date(today.year, today.month, 1)

    raw = str(value).strip()

    try:
        if len(raw) == 7:
            parsed = datetime.strptime(raw, "%Y-%m").date()
            return date(parsed.year, parsed.month, 1)

        parsed = datetime.strptime(raw, "%Y-%m-%d").date()
        return date(parsed.year, parsed.month, 1)
    except ValueError as exc:
        raise ValueError("Некорректный month. Используй YYYY-MM или YYYY-MM-DD") from exc


def _month_bounds(month_value: date) -> tuple[datetime, datetime]:
    start_dt = datetime.combine(month_value, dtime.min)

    if month_value.month == 12:
        next_month = date(month_value.year + 1, 1, 1)
    else:
        next_month = date(month_value.year, month_value.month + 1, 1)

    end_dt = datetime.combine(next_month, dtime.min)
    return start_dt, end_dt


def _parse_datetime_value(value: str | None) -> datetime:
    if not value:
        raise ValueError("Поле date обязательно")

    raw = str(value).strip()
    normalized = raw.replace(" ", "T")

    try:
        return datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError(
            "Некорректная дата. Используй формат YYYY-MM-DDTHH:MM или YYYY-MM-DD HH:MM"
        ) from exc


def _parse_amount_value(value) -> Decimal:
    if value is None or str(value).strip() == "":
        raise ValueError("Поле amount обязательно")

    raw = str(value).strip().replace(",", ".")

    try:
        amount = Decimal(raw)
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("Некорректная сумма") from exc

    if amount <= 0:
        raise ValueError("Сумма должна быть больше 0")

    return amount.quantize(Decimal("0.01"))


def _get_category_for_user(
    user: User,
    category_id,
    tx_type: str,
) -> Category | None:
    if category_id in (None, "", 0, "0"):
        return None

    try:
        category_id_int = int(category_id)
    except (TypeError, ValueError) as exc:
        raise ValueError("Некорректный category_id") from exc

    category = Category.objects.filter(
        id=category_id_int,
        user=user,
    ).first()

    if not category:
        raise ValueError("Категория не найдена")

    if category.type != tx_type:
        raise ValueError("Категория не соответствует типу транзакции")

    return category


def _get_expense_category_for_user(user: User, category_id) -> Category:
    try:
        category_id_int = int(category_id)
    except (TypeError, ValueError) as exc:
        raise ValueError("Некорректный category_id") from exc

    category = Category.objects.filter(
        id=category_id_int,
        user=user,
        type="expense",
    ).first()

    if not category:
        raise ValueError("Категория расходов не найдена")

    return category


def _serialize_transaction(tx: Transaction) -> dict:
    return TransactionSerializer(tx).data


def _serialize_budget(user: User, budget: Budget) -> dict:
    data = BudgetSerializer(budget).data

    start_dt, end_dt = _month_bounds(budget.month)

    spent = (
        Transaction.objects.filter(
            user=user,
            type="expense",
            category_id=budget.category_id,
            date__gte=start_dt,
            date__lt=end_dt,
        ).aggregate(s=Sum("amount"))["s"]
        or Decimal("0")
    )

    limit_amount = Decimal(str(budget.limit_amount))
    remaining = limit_amount - spent

    if limit_amount > 0:
      usage_percent = (spent / limit_amount) * Decimal("100")
    else:
      usage_percent = Decimal("0")

    usage_percent = usage_percent.quantize(Decimal("0.01"))

    if spent > limit_amount:
        status_value = "exceeded"
        status_label = "Превышен"
    elif usage_percent >= Decimal("80.00"):
        status_value = "warning"
        status_label = "Почти исчерпан"
    else:
        status_value = "normal"
        status_label = "Норма"

    data.update(
        {
            "spent_amount": str(spent.quantize(Decimal("0.01"))),
            "remaining_amount": str(remaining.quantize(Decimal("0.01"))),
            "usage_percent": str(usage_percent),
            "status": status_value,
            "status_label": status_label,
        }
    )
    return data


def _build_check_string(init_data_raw: str) -> tuple[str, str]:
    pairs = parse_qsl(init_data_raw, keep_blank_values=True)

    data = []
    received_hash = None

    for key, value in pairs:
        if key == "hash":
            received_hash = value
        else:
            data.append((key, value))

    data.sort(key=lambda item: item[0])
    check_string = "\n".join(f"{key}={value}" for key, value in data)

    return check_string, received_hash or ""


def _validate_telegram_init_data(init_data_raw: str, bot_token: str) -> dict | None:
    if not init_data_raw or not bot_token:
        return None

    check_string, received_hash = _build_check_string(init_data_raw)
    if not received_hash:
        return None

    secret_key = hmac.new(
        key=b"WebAppData",
        msg=bot_token.encode("utf-8"),
        digestmod=hashlib.sha256,
    ).digest()

    calculated_hash = hmac.new(
        key=secret_key,
        msg=check_string.encode("utf-8"),
        digestmod=hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(calculated_hash, received_hash):
        return None

    parsed = dict(parse_qsl(init_data_raw, keep_blank_values=True))
    user_raw = parsed.get("user")
    if not user_raw:
        return None

    try:
        return json.loads(user_raw)
    except json.JSONDecodeError:
        return None


@api_view(["POST"])
def miniapp_auth(request: Request) -> Response:
    init_data = (request.data.get("initData") or "").strip()
    bot_token = os.getenv("BOT_TOKEN", "").strip()

    if not init_data:
        return Response(
            {"detail": "Missing initData"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    if not bot_token:
        return Response(
            {"detail": "BOT_TOKEN is not configured on server"},
            status=status.HTTP_500_INTERNAL_SERVER_ERROR,
        )

    tg_user = _validate_telegram_init_data(init_data, bot_token)
    if not tg_user:
        return Response(
            {"detail": "Invalid Telegram initData"},
            status=status.HTTP_401_UNAUTHORIZED,
        )

    telegram_id = tg_user.get("id")
    if not telegram_id:
        return Response(
            {"detail": "Telegram user id not found"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    username = tg_user.get("username")
    first_name = tg_user.get("first_name")

    user = User.objects.filter(telegram_id=telegram_id).first()

    if not user:
        user = User(
            telegram_id=telegram_id,
            username=username,
            first_name=first_name,
        )

    changed = False

    if username and user.username != username:
        user.username = username
        changed = True

    if first_name and user.first_name != first_name:
        user.first_name = first_name
        changed = True

    if not getattr(user, "api_key", None):
        user.api_key = generate_api_key()
        changed = True

    if changed or not user.pk:
        user.save()

    return Response(
        {
            "api_key": user.api_key,
            "user_id": user.id,
            "telegram_id": user.telegram_id,
            "username": user.username,
            "first_name": user.first_name,
        }
    )


@api_view(["GET"])
def me(request: Request) -> Response:
    user = get_user_from_request(request)
    return Response(
        {
            "id": user.id,
            "telegram_id": user.telegram_id,
            "username": user.username,
            "first_name": user.first_name,
            "created_at": user.created_at,
        }
    )


@api_view(["GET"])
def categories(request: Request) -> Response:
    user = get_user_from_request(request)

    tx_type = request.query_params.get("type")
    qs = Category.objects.filter(user=user).order_by("type", "name")

    if tx_type in ("income", "expense"):
        qs = qs.filter(type=tx_type)

    return Response(CategorySerializer(qs, many=True).data)


@api_view(["GET", "POST"])
def transactions(request: Request) -> Response:
    user = get_user_from_request(request)

    if request.method == "GET":
        qs = Transaction.objects.filter(user=user).select_related(
            "category",
            "suggested_category",
        ).order_by("-date", "-id")

        tx_type = request.query_params.get("type")
        if tx_type in ("income", "expense"):
            qs = qs.filter(type=tx_type)

        category_id = request.query_params.get("category_id")
        if category_id:
            try:
                qs = qs.filter(category_id=int(category_id))
            except ValueError:
                return Response(
                    {"detail": "Некорректный category_id"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        date_from = request.query_params.get("from")
        date_to = request.query_params.get("to")
        search = (request.query_params.get("q") or "").strip()

        if date_from:
            try:
                d1 = _parse_date(date_from)
                qs = qs.filter(date__gte=datetime.combine(d1, dtime.min))
            except ValueError:
                return Response(
                    {"detail": "Некорректный параметр from. Ожидается YYYY-MM-DD"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        if date_to:
            try:
                d2 = _parse_date(date_to)
                qs = qs.filter(date__lte=datetime.combine(d2, dtime.max))
            except ValueError:
                return Response(
                    {"detail": "Некорректный параметр to. Ожидается YYYY-MM-DD"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        if search:
            qs = qs.filter(
                Q(note__icontains=search)
                | Q(category__name__icontains=search)
            )

        limit_raw = request.query_params.get("limit", "500")
        try:
            limit = max(1, min(int(limit_raw), 1000))
        except ValueError:
            return Response(
                {"detail": "Некорректный параметр limit"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        data = TransactionSerializer(qs[:limit], many=True).data
        return Response(data)

    tx_type = (request.data.get("type") or "").strip()
    if tx_type not in ("income", "expense"):
        return Response(
            {"detail": "Поле type должно быть income или expense"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        amount = _parse_amount_value(request.data.get("amount"))
        tx_date = _parse_datetime_value(request.data.get("date"))
        category = _get_category_for_user(
            user=user,
            category_id=request.data.get("category_id"),
            tx_type=tx_type,
        )
    except ValueError as exc:
        return Response(
            {"detail": str(exc)},
            status=status.HTTP_400_BAD_REQUEST,
        )

    note = (request.data.get("note") or "").strip() or None

    tx = Transaction.objects.create(
        user=user,
        category=category,
        amount=amount,
        date=tx_date,
        type=tx_type,
        note=note,
        is_category_accepted=True,
    )

    tx = Transaction.objects.select_related(
        "category",
        "suggested_category",
    ).get(id=tx.id)

    return Response(
        _serialize_transaction(tx),
        status=status.HTTP_201_CREATED,
    )


@api_view(["GET", "PATCH", "DELETE"])
def transaction_detail(request: Request, tx_id: int) -> Response:
    user = get_user_from_request(request)

    tx = (
        Transaction.objects.select_related("category", "suggested_category")
        .filter(id=tx_id, user=user)
        .first()
    )

    if not tx:
        return Response(
            {"detail": "Транзакция не найдена"},
            status=status.HTTP_404_NOT_FOUND,
        )

    if request.method == "GET":
        return Response(_serialize_transaction(tx))

    if request.method == "DELETE":
        tx.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    new_type = request.data.get("type", tx.type)
    if new_type not in ("income", "expense"):
        return Response(
            {"detail": "Поле type должно быть income или expense"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    try:
        amount = _parse_amount_value(request.data.get("amount", tx.amount))
        tx_date = _parse_datetime_value(request.data.get("date", tx.date))
        category = _get_category_for_user(
            user=user,
            category_id=request.data.get(
                "category_id",
                tx.category_id if tx.category_id else None,
            ),
            tx_type=new_type,
        )
    except ValueError as exc:
        return Response(
            {"detail": str(exc)},
            status=status.HTTP_400_BAD_REQUEST,
        )

    note = request.data.get("note", tx.note)
    note = (str(note).strip() if note is not None else None) or None

    tx.type = new_type
    tx.amount = amount
    tx.date = tx_date
    tx.category = category
    tx.note = note
    tx.is_category_accepted = True
    tx.save()

    tx = (
        Transaction.objects.select_related("category", "suggested_category")
        .filter(id=tx.id, user=user)
        .first()
    )

    return Response(_serialize_transaction(tx))


@api_view(["GET"])
def summary(request: Request) -> Response:
    user = get_user_from_request(request)

    qs = Transaction.objects.filter(user=user)

    tx_type = request.query_params.get("type")
    if tx_type in ("income", "expense"):
        qs = qs.filter(type=tx_type)

    category_id = request.query_params.get("category_id")
    if category_id:
        try:
            qs = qs.filter(category_id=int(category_id))
        except ValueError:
            return Response(
                {"detail": "Некорректный category_id"},
                status=status.HTTP_400_BAD_REQUEST,
            )

    date_from = request.query_params.get("from")
    date_to = request.query_params.get("to")
    search = (request.query_params.get("q") or "").strip()

    if date_from:
        try:
            d1 = _parse_date(date_from)
            qs = qs.filter(date__gte=datetime.combine(d1, dtime.min))
        except ValueError:
            return Response(
                {"detail": "Некорректный параметр from. Ожидается YYYY-MM-DD"},
                status=status.HTTP_400_BAD_REQUEST,
            )

    if date_to:
        try:
            d2 = _parse_date(date_to)
            qs = qs.filter(date__lte=datetime.combine(d2, dtime.max))
        except ValueError:
            return Response(
                {"detail": "Некорректный параметр to. Ожидается YYYY-MM-DD"},
                status=status.HTTP_400_BAD_REQUEST,
            )

    if search:
        qs = qs.filter(
            Q(note__icontains=search)
            | Q(category__name__icontains=search)
        )

    income = qs.filter(type="income").aggregate(s=Sum("amount"))["s"] or Decimal("0")
    expense = qs.filter(type="expense").aggregate(s=Sum("amount"))["s"] or Decimal("0")
    balance = income - expense

    return Response(
        {
            "income": str(income),
            "expense": str(expense),
            "balance": str(balance),
            "transactions_count": qs.count(),
        }
    )


@api_view(["GET", "POST"])
def budgets(request: Request) -> Response:
    user = get_user_from_request(request)

    if request.method == "GET":
        try:
            month_value = _parse_month_value(request.query_params.get("month"))
        except ValueError as exc:
            return Response(
                {"detail": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        qs = Budget.objects.filter(
            user=user,
            month=month_value,
        ).select_related("category").order_by("category__name", "id")

        category_id = request.query_params.get("category_id")
        if category_id:
            try:
                qs = qs.filter(category_id=int(category_id))
            except ValueError:
                return Response(
                    {"detail": "Некорректный category_id"},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        data = [_serialize_budget(user, budget) for budget in qs]
        return Response(data)

    try:
        category = _get_expense_category_for_user(
            user=user,
            category_id=request.data.get("category_id"),
        )
        month_value = _parse_month_value(request.data.get("month"))
        limit_amount = _parse_amount_value(request.data.get("limit_amount"))
    except ValueError as exc:
        return Response(
            {"detail": str(exc)},
            status=status.HTTP_400_BAD_REQUEST,
        )

    budget, _created = Budget.objects.update_or_create(
        user=user,
        category=category,
        month=month_value,
        defaults={
            "limit_amount": limit_amount,
        },
    )

    budget = Budget.objects.select_related("category").get(id=budget.id)
    return Response(
        _serialize_budget(user, budget),
        status=status.HTTP_201_CREATED,
    )


@api_view(["GET", "PATCH", "DELETE"])
def budget_detail(request: Request, budget_id: int) -> Response:
    user = get_user_from_request(request)

    budget = (
        Budget.objects.select_related("category")
        .filter(id=budget_id, user=user)
        .first()
    )

    if not budget:
        return Response(
            {"detail": "Бюджет не найден"},
            status=status.HTTP_404_NOT_FOUND,
        )

    if request.method == "GET":
        return Response(_serialize_budget(user, budget))

    if request.method == "DELETE":
        budget.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    try:
        category = _get_expense_category_for_user(
            user=user,
            category_id=request.data.get("category_id", budget.category_id),
        )
        month_value = _parse_month_value(request.data.get("month", budget.month))
        limit_amount = _parse_amount_value(
            request.data.get("limit_amount", budget.limit_amount)
        )
    except ValueError as exc:
        return Response(
            {"detail": str(exc)},
            status=status.HTTP_400_BAD_REQUEST,
        )

    budget.category = category
    budget.month = month_value
    budget.limit_amount = limit_amount

    try:
        budget.save()
    except IntegrityError:
        return Response(
            {"detail": "Бюджет для этой категории и месяца уже существует"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    budget = Budget.objects.select_related("category").get(id=budget.id)
    return Response(_serialize_budget(user, budget))


@api_view(["GET"])
def budgets_summary(request: Request) -> Response:
    user = get_user_from_request(request)

    try:
        month_value = _parse_month_value(request.query_params.get("month"))
    except ValueError as exc:
        return Response(
            {"detail": str(exc)},
            status=status.HTTP_400_BAD_REQUEST,
        )

    budgets_qs = Budget.objects.filter(
        user=user,
        month=month_value,
    ).select_related("category").order_by("category__name", "id")

    budget_items = [_serialize_budget(user, budget) for budget in budgets_qs]

    total_limit = Decimal("0")
    total_spent = Decimal("0")
    total_remaining = Decimal("0")
    exceeded_count = 0
    warning_count = 0
    normal_count = 0

    for item in budget_items:
        total_limit += Decimal(item["limit_amount"])
        total_spent += Decimal(item["spent_amount"])
        total_remaining += Decimal(item["remaining_amount"])

        if item["status"] == "exceeded":
            exceeded_count += 1
        elif item["status"] == "warning":
            warning_count += 1
        else:
            normal_count += 1

    days_in_month = monthrange(month_value.year, month_value.month)[1]
    month_label = f"{month_value.year}-{month_value.month:02d}"

    return Response(
        {
            "month": str(month_value),
            "month_label": month_label,
            "days_in_month": days_in_month,
            "budgets_count": len(budget_items),
            "total_limit": str(total_limit.quantize(Decimal("0.01"))),
            "total_spent": str(total_spent.quantize(Decimal("0.01"))),
            "total_remaining": str(total_remaining.quantize(Decimal("0.01"))),
            "exceeded_count": exceeded_count,
            "warning_count": warning_count,
            "normal_count": normal_count,
            "items": budget_items,
        }
    )