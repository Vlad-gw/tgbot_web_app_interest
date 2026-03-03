# web/finance/views.py

from django.shortcuts import render


def login_page(request):
    return render(request, "finance/login.html")


def app_page(request):
    return render(request, "finance/app.html")