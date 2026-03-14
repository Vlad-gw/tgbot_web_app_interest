from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("finance.urls")),
    path("miniapp/", include("finance.web_urls")),
]