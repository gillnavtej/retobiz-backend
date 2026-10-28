"""The ONLY place that changes Product.stock_qty."""
from django.db import IntegrityError, transaction

from catalog.models import Product
from common.exceptions import BusinessValidationError, IdempotencyConflict, InsufficientStock

from .models import StockMovement


def lock_products(store, product_ids):
    """Lock rows in ascending id order (prevents deadlocks). Must run inside atomic()."""
    products = {
        p.id: p
        for p in Product.objects.select_for_update().filter(store=store, id__in=set(product_ids)).order_by("id")
    }
    return products


def apply_stock_change(
    *, product, delta, movement_type, user, reference_type="", reference_id=None,
    transaction_ref="", reason="",
):
    """Apply a signed delta to an ALREADY LOCKED product and append a ledger row."""
    new_balance = product.stock_qty + delta
    if new_balance < 0:
        raise InsufficientStock(
            f"Only {product.stock_qty} unit(s) of '{product.name}' available.",
            {"product_id": product.id, "available": product.stock_qty, "requested": -delta},
        )
    product.stock_qty = new_balance
    product.save(update_fields=["stock_qty", "updated_at"])
    return StockMovement.objects.create(
        store=product.store, product=product, movement_type=movement_type,
        quantity_delta=delta, balance_after=new_balance, reference_type=reference_type,
        reference_id=reference_id, transaction_ref=transaction_ref, reason=reason, created_by=user,
    )


def adjust_stock(*, store, user, product_id, quantity_delta, reason, reference=""):
    """Admin stock adjustment. Returns (movement, created)."""

    def existing():
        return StockMovement.objects.filter(
            store=store, movement_type=StockMovement.Type.ADJUSTMENT, transaction_ref=reference
        ).first() if reference else None

    def resolve(mv):
        if mv.product_id == product_id and mv.quantity_delta == quantity_delta:
            return mv, False
        raise IdempotencyConflict("This adjustment reference was already used with different content.")

    if (mv := existing()):
        return resolve(mv)
    try:
        with transaction.atomic():
            products = lock_products(store, [product_id])
            product = products.get(product_id)
            if product is None:
                raise BusinessValidationError("Unknown product.", {"product_id": product_id})
            mv = apply_stock_change(
                product=product, delta=quantity_delta, movement_type=StockMovement.Type.ADJUSTMENT,
                user=user, reference_type="ADJUSTMENT", transaction_ref=reference, reason=reason,
            )
            return mv, True
    except IntegrityError:
        if (mv := existing()):
            return resolve(mv)
        raise
