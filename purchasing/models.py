from django.conf import settings
from django.db import models
from django.db.models import Q


class Supplier(models.Model):
    store = models.ForeignKey("catalog.Store", on_delete=models.PROTECT, related_name="suppliers")
    name = models.CharField(max_length=150)
    gstin = models.CharField(max_length=15, blank=True)
    phone = models.CharField(max_length=20, blank=True)

    def __str__(self):
        return self.name


class Purchase(models.Model):
    store = models.ForeignKey("catalog.Store", on_delete=models.PROTECT, related_name="purchases")
    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT, related_name="purchases")
    reference = models.CharField(max_length=100)
    request_hash = models.CharField(max_length=64)
    total_amount = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["store", "reference"], name="uniq_purchase_store_reference")]


class PurchaseItem(models.Model):
    purchase = models.ForeignKey(Purchase, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey("catalog.Product", on_delete=models.PROTECT, related_name="+")
    quantity = models.PositiveIntegerField()
    purchase_rate = models.DecimalField(max_digits=12, decimal_places=2)
    line_total = models.DecimalField(max_digits=14, decimal_places=2)

    class Meta:
        constraints = [models.CheckConstraint(check=Q(quantity__gt=0), name="purchaseitem_qty_positive")]
