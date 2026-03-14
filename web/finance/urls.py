from django.urls import path

from .api import (
    budget_detail,
    budgets,
    budgets_summary,
    categories,
    health,
    me,
    miniapp_auth,
    summary,
    transaction_detail,
    transactions,
)

urlpatterns = [
    path("health/", health),
    path("miniapp/auth/", miniapp_auth),
    path("me/", me),
    path("categories/", categories),
    path("transactions/", transactions),
    path("transactions/<int:tx_id>/", transaction_detail),
    path("summary/", summary),
    path("budgets/", budgets),
    path("budgets/<int:budget_id>/", budget_detail),
    path("budgets/summary/", budgets_summary),
]