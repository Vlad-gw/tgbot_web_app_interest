# web/finance/views.py

from django.shortcuts import render
from django.views.decorators.clickjacking import xframe_options_exempt


@xframe_options_exempt
def mini_app_page(request):
    response = render(request, "finance/mini_app.html")
    return response