from django.conf import settings
from django.db import models
from django.db.models import Q


class AppendOnlyError(Exception):
    pass


class AppendOnlyQuerySet(models.QuerySet):
    def update(self, **kwargs):
        raise AppendOnlyError("StockMovement is append-only.")

    def delete(self):
        raise AppendOnlyError("StockMovement is append-only.")

    def bulk_update(self, *a, **kw):
        raise AppendOnlyError("StockMovement is append-only.")


class StockMovement(models.Model):
    class Type(models.TextChoices):
        PURCHASE = "PURCHASE", "Purchase"
        SALE = "SALE", "Sale"
        ADJUSTMENT = "ADJUSTMENT", "Adjustment"

    store = models.ForeignKey("catalog.Store", on_delete=models.PROTECT, related_name="movements")
    product = models.ForeignKey("catalog.Product", on_delete=models.PROTECT, related_name="movements")
    movement_type = models.CharField(max_length=12, choices=Type.choices)
    quantity_delta = models.IntegerField()  # signed
    balance_after = models.IntegerField()
    reference_type = models.CharField(max_length=20, blank=True)
    reference_id = models.BigIntegerField(null=True, blank=True)
    transaction_ref = models.CharField(max_length=100, blank=True)
    reason = models.CharField(max_length=255, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="+")
    created_at = models.DateTimeField(auto_now_add=True)

    objects = AppendOnlyQuerySet.as_manager()

    class Meta:
        indexes = [
            models.Index(fields=["product", "created_at"], name="mov_product_created_idx"),
            models.Index(fields=["transaction_ref"], name="mov_txn_ref_idx"),
        ]
        constraints = [
            models.CheckConstraint(check=~Q(quantity_delta=0), name="movement_delta_nonzero"),
            models.CheckConstraint(check=Q(balance_after__gte=0), name="movement_balance_non_negative"),
            # Defence in depth: the same document can never move the same product twice.
            models.UniqueConstraint(
                fields=["store", "product", "movement_type", "transaction_ref"],
                condition=~Q(transaction_ref=""),
                name="uniq_movement_per_document_product",
            ),
        ]
        ordering = ["id"]

    def save(self, *args, **kwargs):
        if self.pk is not None:
            raise AppendOnlyError("StockMovement is append-only.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise AppendOnlyError("StockMovement is append-only.")
