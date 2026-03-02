from django.db import models


class User(models.Model):
    id = models.AutoField(primary_key=True)
    telegram_id = models.BigIntegerField(unique=True, null=True, blank=True)
    username = models.TextField(null=True, blank=True)
    first_name = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(null=True, blank=True)
    api_key = models.TextField(null=True, blank=True)

    class Meta:
        managed = False
        db_table = "users"

    def __str__(self) -> str:
        return self.username or self.first_name or str(self.telegram_id) or f"User#{self.id}"


class Category(models.Model):
    id = models.AutoField(primary_key=True)
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        db_column="user_id",
        related_name="categories",
        null=True,
        blank=True,
    )
    name = models.TextField()
    type = models.TextField()  # income / expense

    class Meta:
        managed = False
        db_table = "categories"

    def __str__(self) -> str:
        return f"{self.name} ({self.type})"


class Transaction(models.Model):
    id = models.AutoField(primary_key=True)

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        db_column="user_id",
        related_name="transactions",
        null=True,
        blank=True,
    )

    category = models.ForeignKey(
        Category,
        on_delete=models.SET_NULL,
        db_column="category_id",
        related_name="transactions",
        null=True,
        blank=True,
    )

    amount = models.DecimalField(max_digits=10, decimal_places=2)
    date = models.DateTimeField()  # timestamp without time zone
    type = models.TextField()      # income / expense
    note = models.TextField(null=True, blank=True)

    suggested_category = models.ForeignKey(
        Category,
        on_delete=models.SET_NULL,
        db_column="suggested_category_id",
        related_name="suggested_transactions",
        null=True,
        blank=True,
    )

    is_category_accepted = models.BooleanField(default=True)
    created_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        managed = False
        db_table = "transactions"

    def __str__(self) -> str:
        return f"{self.type} {self.amount} ({self.date:%Y-%m-%d})"

