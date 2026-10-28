from django.conf import settings
from django.db import models
from django.db.models import Q


class Sale(models.Model):
    store = models.ForeignKey("catalog.Store", on_delete=models.PROTECT, related_name="sales")
    bill_no = models.CharField(max_length=40)
    transaction_id = models.UUIDField()
    request_hash = models.CharField(max_length=64)
    subtotal = models.DecimalField(max_digits=14, decimal_places=2, default=0)  # taxable value
    tax_total = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    grand_total = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    status = models.CharField(max_length=12, default="COMPLETED")
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="sales")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["store", "transaction_id"], name="uniq_sale_store_txn"),
            models.UniqueConstraint(fields=["store", "bill_no"], name="uniq_sale_store_billno"),
        ]
        indexes = [models.Index(fields=["store", "created_at"], name="sale_store_created_idx")]


class PriceOverrideApproval(models.Model):
    store = models.ForeignKey("catalog.Store", on_delete=models.PROTECT, related_name="override_approvals")
    product = models.ForeignKey("catalog.Product", on_delete=models.PROTECT, related_name="+")
    original_rate = models.DecimalField(max_digits=12, decimal_places=2)
    requested_rate = models.DecimalField(max_digits=12, decimal_places=2)
    reason = models.CharField(max_length=255)
    approved_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)
    used_at = models.DateTimeField(null=True, blank=True)
    used_in_sale_item = models.OneToOneField(
        "sales.SaleItem", null=True, blank=True, on_delete=models.PROTECT, related_name="approval_used"
    )

    class Meta:
        constraints = [
            models.CheckConstraint(check=Q(requested_rate__gte=0), name="override_rate_non_negative"),
        ]


class SaleItem(models.Model):
    sale = models.ForeignKey(Sale, on_delete=models.CASCADE, related_name="items")
    product = models.ForeignKey("catalog.Product", on_delete=models.PROTECT, related_name="+")
    quantity = models.PositiveIntegerField()
    mrp_snapshot = models.DecimalField(max_digits=12, decimal_places=2)
    rate_applied = models.DecimalField(max_digits=12, decimal_places=2)
    gst_rate_snapshot = models.DecimalField(max_digits=5, decimal_places=2)
    taxable_value = models.DecimalField(max_digits=14, decimal_places=2)
    cgst = models.DecimalField(max_digits=14, decimal_places=2)
    sgst = models.DecimalField(max_digits=14, decimal_places=2)
    line_total = models.DecimalField(max_digits=14, decimal_places=2)
    override_approval = models.ForeignKey(
        PriceOverrideApproval, null=True, blank=True, on_delete=models.PROTECT, related_name="sale_lines"
    )

    class Meta:
        constraints = [models.CheckConstraint(check=Q(quantity__gt=0), name="saleitem_qty_positive")]
