from rest_framework import serializers
from .models import Transaction


class TransactionSerializer(serializers.ModelSerializer):
    category_name = serializers.CharField(source="category.name", read_only=True)

    class Meta:
        model = Transaction
        fields = [
            "id",
            "type",
            "amount",
            "date",
            "note",
            "is_category_accepted",
            "category",
            "category_name",
            "suggested_category",
        ]
