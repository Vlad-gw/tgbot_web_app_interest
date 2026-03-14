from django.urls import path

from .api import (
    health,
    transactions,
    summary,
    me,
    miniapp_auth,
)

urlpatterns = [
    path("health/", health),
    path("miniapp/auth/", miniapp_auth),
    path("me/", me),
    path("transactions/", transactions),
    path("summary/", summary),
]