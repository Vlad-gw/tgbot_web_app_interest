from __future__ import annotations

import hashlib
import os
from datetime import datetime, time as dtime

from django.conf import settings
from django.db.models import Sum
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.request import Request
from rest_framework.response import Response

from .auth import generate_api_key, get_user_from_request
from .models import Transaction, User, AuthCode
from .serializers import TransactionSerializer


@api_view(["GET"])
def health(_request: Request) -> Response:
    return Response({"ok": True})


def _parse_date(s: str):
    return datetime.strptime(s, "%Y-%m-%d").date()


def _hash_login_code(code: str) -> str:
    pepper = os.getenv("AUTH_CODE_PEPPER") or getattr(settings, "AUTH_CODE_PEPPER", "")
    return hashlib.sha256((pepper + code).encode("utf-8")).hexdigest()


@csrf_exempt
@api_view(["POST"])
def auth_code(request: Request) -> Response:
    """
    Авторизация по одноразовому коду из бота.
    Ожидает JSON: {"code": "12345678"}
    Возвращает: {"api_key": "...", "user_id": ..., "telegram_id": ...}
    """
    code = (request.data.get("code") or "").strip().replace(" ", "")
    if not code:
        return Response({"detail": "Missing code"}, status=status.HTTP_400_BAD_REQUEST)

    code_hash = _hash_login_code(code)

    row = (
        AuthCode.objects
        .filter(code_hash=code_hash, used_at__isnull=True, expires_at__gte=timezone.now())
        .order_by("-id")
        .first()
    )
    if not row:
        return Response({"detail": "Invalid or expired code"}, status=status.HTTP_401_UNAUTHORIZED)

    telegram_id = int(row.telegram_id)

    # делаем код одноразовым
    row.used_at = timezone.now()
    row.save(update_fields=["used_at"])

    user = User.objects.filter(telegram_id=telegram_id).first()
    if not user:
        user = User(telegram_id=telegram_id)

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

    data = TransactionSerializer(qs[:500], many=True).data
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