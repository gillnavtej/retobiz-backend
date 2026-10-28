import hashlib
import json

from django.db import IntegrityError, transaction

from common.exceptions import BusinessValidationError, IdempotencyConflict
from common.money import round2
from inventory.models import StockMovement
from inventory.services import apply_stock_change, lock_products
from decimal import Decimal # Ensure Decimal is imported at the top of the file

from .models import Purchase, PurchaseItem, Supplier


def _hash(supplier_id, items):
    norm = {
        "supplier_id": supplier_id,
        "items": sorted(
            [[i["product_id"], i["quantity"], str(i["purchase_rate"])] for i in items]
        ),
    }
    return hashlib.sha256(json.dumps(norm, sort_keys=True).encode()).hexdigest()


def create_purchase(*, store, user, reference, supplier_id, items):
    """Returns (purchase, created). Idempotent on (store, reference)."""
    request_hash = _hash(supplier_id, items)

    def existing():
        return Purchase.objects.filter(store=store, reference=reference).first()

    def resolve(p):
        if p.request_hash == request_hash:
            return p, False
        raise IdempotencyConflict("This purchase reference was already used with different content.")

    if (p := existing()):
        return resolve(p)
    try:
        with transaction.atomic():
            supplier = Supplier.objects.filter(store=store, id=supplier_id).first()
            if supplier is None:
                raise BusinessValidationError("Unknown supplier.", {"supplier_id": supplier_id})
            purchase = Purchase.objects.create(
                store=store, supplier=supplier, reference=reference,
                request_hash=request_hash, created_by=user,
            )  # unique index: a parallel duplicate blocks here, then fails with IntegrityError
            products = lock_products(store, [i["product_id"] for i in items])
            total = 0
            for line in sorted(items, key=lambda i: i["product_id"]):
                product = products.get(line["product_id"])
                if product is None:
                    raise BusinessValidationError("Unknown product.", {"product_id": line["product_id"]})
                # line_total = round2(line["purchase_rate"] * line["quantity"])
                line_total = round2(Decimal(str(line["purchase_rate"])) * line["quantity"])
                PurchaseItem.objects.create(
                    purchase=purchase, product=product, quantity=line["quantity"],
                    purchase_rate=line["purchase_rate"], line_total=line_total,
                )
                apply_stock_change(
                    product=product, delta=line["quantity"], movement_type=StockMovement.Type.PURCHASE,
                    user=user, reference_type="PURCHASE", reference_id=purchase.id,
                    transaction_ref=reference,
                )
                total += line_total
            purchase.total_amount = total
            purchase.save(update_fields=["total_amount"])
            return purchase, True
    except IntegrityError:
        if (p := existing()):
            return resolve(p)
        raise
