from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    class Role(models.TextChoices):
        ADMIN = "ADMIN", "Admin"
        CASHIER = "CASHIER", "Cashier"

    store = models.ForeignKey("catalog.Store", on_delete=models.PROTECT, related_name="users", null=True)
    role = models.CharField(max_length=10, choices=Role.choices, default=Role.CASHIER)

    @property
    def is_admin_role(self):
        return self.role == self.Role.ADMIN
