from __future__ import annotations

import hashlib
import hmac
import json
import os
from datetime import datetime, time as dtime
from urllib.parse import parse_qsl

from django.db.models import Sum
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.request import Request
from rest_framework.response import Response

from .auth import generate_api_key, get_user_from_request
from .models import Transaction, User
from .serializers import TransactionSerializer


@api_view(["GET"])
def health(_request: Request) -> Response:
    return Response({"ok": True})


def _parse_date(s: str):
    return datetime.strptime(s, "%Y-%m-%d").date()


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
    """
    Авторизация через Telegram Mini App.
    Ожидает JSON:
    {
        "initData": "query_id=...&user=...&auth_date=...&hash=..."
    }

    Возвращает:
    {
        "api_key": "...",
        "user_id": 1,
        "telegram_id": 123,
        "username": "...",
        "first_name": "..."
    }
    """
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
def transactions(request: Request) -> Response:
    user = get_user_from_request(request)

    qs = Transaction.objects.filter(user=user).order_by("-date", "-id")

    tx_type = request.query_params.get("type")
    if tx_type in ("income", "expense"):
        qs = qs.filter(type=tx_type)

    date_from = request.query_params.get("from")
    date_to = request.query_params.get("to")

    if date_from:
        d1 = _parse_date(date_from)
        qs = qs.filter(date__gte=datetime.combine(d1, dtime.min))

    if date_to:
        d2 = _parse_date(date_to)
        qs = qs.filter(date__lte=datetime.combine(d2, dtime.max))

    data = TransactionSerializer(qs[:500], many=True).data
    return Response(data)


@api_view(["GET"])
def summary(request: Request) -> Response:
    user = get_user_from_request(request)

    qs = Transaction.objects.filter(user=user)

    date_from = request.query_params.get("from")
    date_to = request.query_params.get("to")

    if date_from:
        d1 = _parse_date(date_from)
        qs = qs.filter(date__gte=datetime.combine(d1, dtime.min))

    if date_to:
        d2 = _parse_date(date_to)
        qs = qs.filter(date__lte=datetime.combine(d2, dtime.max))

    income = qs.filter(type="income").aggregate(s=Sum("amount"))["s"] or 0
    expense = qs.filter(type="expense").aggregate(s=Sum("amount"))["s"] or 0

    return Response(
        {
            "income": str(income),
            "expense": str(expense),
            "balance": str(income - expense),
        }
    )