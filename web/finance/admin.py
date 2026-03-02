from django.contrib import admin
from .models import User, Category, Transaction


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ("id", "telegram_id", "username", "first_name", "created_at")
    search_fields = ("telegram_id", "username", "first_name")
    ordering = ("-id",)


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "type", "name")
    list_filter = ("type",)
    search_fields = ("name",)
    ordering = ("user_id", "type", "name")


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "type", "amount", "date", "category", "is_category_accepted")
    list_filter = ("type", "date", "is_category_accepted")
    search_fields = ("note",)
    raw_id_fields = ("user", "category", "suggested_category")
    ordering = ("-date", "-id")
