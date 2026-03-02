from django.shortcuts import render
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from rest_framework.decorators import api_view
from rest_framework import status
from rest_framework.response import Response

from .auth import generate_api_key
from .models import User
from .api import _check_telegram_auth  # если у тебя эта функция в api.py

def login_page(request):
    return render(request, "finance/login.html")


def app_page(request):
    return render(request, "finance/app.html")

@csrf_exempt
@api_view(["POST"])
def auth_telegram_page(request):
    payload = dict(request.data)

    if not _check_telegram_auth(payload):
        return Response({"detail": "Telegram auth failed"}, status=status.HTTP_401_UNAUTHORIZED)

    telegram_id = int(payload["id"])
    username = payload.get("username")
    first_name = payload.get("first_name")

    user = User.objects.filter(telegram_id=telegram_id).first()
    if not user:
        user = User(telegram_id=telegram_id)

    if username is not None:
        user.username = username
    if first_name is not None:
        user.first_name = first_name

    if not user.api_key:
        user.api_key = generate_api_key()

    user.save()

    display_name = user.username or user.first_name or str(user.telegram_id)

    # возвращаем HTML страницу
    return Response(
        render(
            request._request,
            "finance/auth_result.html",
            {"api_key": user.api_key, "display_name": display_name},
        ).content,
        content_type="text/html",
    )