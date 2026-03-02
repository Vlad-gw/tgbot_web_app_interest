# web/finance/api.py

from __future__ import annotations

import hashlib
import hmac
import os
from datetime import datetime, time as dtime
from typing import Any, Dict

from django.conf import settings
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
    """
    Parse date in YYYY-MM-DD format to python date.
    """
    return datetime.strptime(s, "%Y-%m-%d").date()


def _check_telegram_auth(data: Dict[str, Any]) -> bool:
    """
    Проверка подписи Telegram Login Widget.
    data содержит поля: id, username, first_name, auth_date, hash, ...
    """
    received_hash = data.get("hash")
    if not received_hash:
        return False

    auth_data = {k: v for k, v in data.items() if k != "hash"}
    pairs = [f"{k}={auth_data[k]}" for k in sorted(auth_data.keys())]
    data_check_string = "\n".join(pairs)

    bot_token = os.getenv("BOT_TOKEN") or getattr(settings, "BOT_TOKEN", "")
    if not bot_token:
        return False

    secret_key = hashlib.sha256(bot_token.encode()).digest()
    calculated_hash = hmac.new(
        secret_key, data_check_string.encode(), hashlib.sha256
    ).hexdigest()

    return hmac.compare_digest(calculated_hash, received_hash)


@api_view(["POST"])
def auth_telegram(request: Request) -> Response:
    payload: Dict[str, Any] = dict(request.data)

    if not _check_telegram_auth(payload):
        return Response(
            {"detail": "Telegram auth failed"},
            status=status.HTTP_401_UNAUTHORIZED,
        )

    telegram_id = int(payload["id"])
    username = payload.get("username")
    first_name = payload.get("first_name")

    user = User.objects.filter(telegram_id=telegram_id).first()
    if not user:
        user = User(telegram_id=telegram_id, username=username, first_name=first_name)

    # обновим данные, если поменялись
    if username is not None:
        user.username = username
    if first_name is not None:
        user.first_name = first_name

    if not getattr(user, "api_key", None):
        user.api_key = generate_api_key()

    user.save()

    return Response(
        {
            "api_key": user.api_key,
            "user_id": user.id,
            "telegram_id": user.telegram_id,
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
    """
    Return transactions ONLY for current user (by X-API-KEY or api_key query param).
    Optional filters:
      - type=income|expense
      - from=YYYY-MM-DD
      - to=YYYY-MM-DD
    """
    user = get_user_from_request(request)

    qs = Transaction.objects.filter(user=user).order_by("-date", "-id")

    t = request.query_params.get("type")
    if t in ("income", "expense"):
        qs = qs.filter(type=t)

    date_from = request.query_params.get("from")
    date_to = request.query_params.get("to")

    if date_from:
        d1 = _parse_date(date_from)
        qs = qs.filter(date__gte=datetime.combine(d1, dtime.min))
    if date_to:
        d2 = _parse_date(date_to)
        qs = qs.filter(date__lte=datetime.combine(d2, dtime.max))

    data = TransactionSerializer(qs[:500], many=True).data  # лимит для старта
    return Response(data)


@api_view(["GET"])
def summary(request: Request) -> Response:
    """
    Return income/expense/balance ONLY for current user.
    Optional filters:
      - from=YYYY-MM-DD
      - to=YYYY-MM-DD
    """
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
