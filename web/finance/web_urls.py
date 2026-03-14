from django.urls import path
from .views import mini_app_page

urlpatterns = [
    path("", mini_app_page, name="mini_app"),
]