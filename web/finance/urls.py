from django.urls import path
from .api import health, transactions, summary, auth_telegram, me
from .views import auth_telegram_page


urlpatterns = [
    path("health/", health),
    path("auth/telegram/", auth_telegram),
    path("me/", me),
    path("transactions/", transactions),
    path("summary/", summary),

]
