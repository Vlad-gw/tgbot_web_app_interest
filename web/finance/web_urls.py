from django.urls import path
from .views import login_page, app_page

urlpatterns = [
    path("login/", login_page),
    path("app/", app_page),
]
