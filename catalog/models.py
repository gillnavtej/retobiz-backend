from django.db import models
from django.db.models import F, Q


class Store(models.Model):
    name = models.CharField(max_length=120)
    code = models.CharField(max_length=20, unique=True)
    state_code = models.CharField(max_length=2, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name


class Product(models.Model):
    store = models.ForeignKey(Store, on_delete=models.PROTECT, related_name="products")
    name = models.CharField(max_length=200)
    barcode = models.CharField(max_length=64)
    mrp = models.DecimalField(max_digits=12, decimal_places=2)
    purchase_rate = models.DecimalField(max_digits=12, decimal_places=2)
    selling_rate = models.DecimalField(max_digits=12, decimal_places=2)
    gst_rate = models.DecimalField(max_digits=5, decimal_places=2)
    # Only inventory.services.apply_stock_change() may modify this field.
    stock_qty = models.IntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["store", "barcode"], name="uniq_product_store_barcode"),
            models.CheckConstraint(check=Q(stock_qty__gte=0), name="stock_qty_non_negative"),
            models.CheckConstraint(check=Q(selling_rate__lte=F("mrp")), name="selling_rate_lte_mrp"),
            models.CheckConstraint(
                check=Q(mrp__gte=0, purchase_rate__gte=0, selling_rate__gte=0),
                name="product_rates_non_negative",
            ),
            models.CheckConstraint(
                check=Q(gst_rate__gte=0, gst_rate__lte=28), name="product_gst_range"
            ),
        ]
        indexes = [models.Index(fields=["store", "name"], name="product_store_name_idx")]

    def __str__(self):
        return f"{self.name} ({self.barcode})"
