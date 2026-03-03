from django.urls import path

from .api import health, transactions, summary, auth_code, me

urlpatterns = [
    path("health/", health),
    path("auth/code/", auth_code),
    path("me/", me),
    path("transactions/", transactions),
    path("summary/", summary),
]