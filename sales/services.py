import hashlib
import json
import uuid

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from catalog.models import Product
from common.exceptions import (
    BusinessValidationError, IdempotencyConflict, InsufficientStock, InvalidOverride,
)
from common.money import HUNDRED, round2, split_inclusive_line
from inventory.models import StockMovement
from inventory.services import apply_stock_change, lock_products

from .models import PriceOverrideApproval, Sale, SaleItem


def _hash(items):
    norm = sorted([i["product_id"], i["quantity"], i.get("override_approval_id")] for i in items)
    return hashlib.sha256(json.dumps(norm).encode()).hexdigest()


def issue_override(*, store, admin_user, product_id, requested_rate, reason):
    product = Product.objects.filter(store=store, id=product_id).first()
    if product is None:
        raise BusinessValidationError("Unknown product.", {"product_id": product_id})
    if requested_rate >= product.selling_rate:
        raise BusinessValidationError("Override rate must be lower than the current selling rate.")
    floor = product.selling_rate * (HUNDRED - settings.PRICE_OVERRIDE_MAX_DISCOUNT_PERCENT) / HUNDRED
    if requested_rate < round2(floor):
        raise BusinessValidationError(
            f"Discount exceeds the allowed {settings.PRICE_OVERRIDE_MAX_DISCOUNT_PERCENT}%."
        )
    return PriceOverrideApproval.objects.create(
        store=store, product=product, original_rate=product.selling_rate,
        requested_rate=requested_rate, reason=reason, approved_by=admin_user,
    )


def _resolve_rate(store, product, approval_id):
    """Returns (rate, approval_or_None). Locks the approval row."""
    if approval_id is None:
        return product.selling_rate, None
    approval = PriceOverrideApproval.objects.select_for_update().filter(id=approval_id, store=store).first()
    if approval is None:
        raise InvalidOverride("Override approval not found.", {"approval_id": approval_id})
    if approval.used_at is not None:
        raise InvalidOverride("Override approval was already used.", {"approval_id": approval_id})
    if approval.product_id != product.id:
        raise InvalidOverride("Override approval is for a different product.", {"approval_id": approval_id})
    if approval.original_rate != product.selling_rate:
        raise InvalidOverride("Product rate changed since approval; request a new one.", {"approval_id": approval_id})
    return approval.requested_rate, approval


def create_sale(*, store, user, transaction_id: uuid.UUID, items):
    """Returns (sale, created). Idempotent on (store, transaction_id)."""
    request_hash = _hash(items)

    def existing():
        return Sale.objects.filter(store=store, transaction_id=transaction_id).first()

    def resolve(sale):
        if sale.request_hash == request_hash:
            return sale, False
        raise IdempotencyConflict()

    if (sale := existing()):
        return resolve(sale)

    try:
        with transaction.atomic():
            # Inserted FIRST: a parallel request with the same transaction_id blocks on the
            # unique index until we commit, then fails with IntegrityError -> replay path.
            sale = Sale.objects.create(
                store=store, transaction_id=transaction_id, request_hash=request_hash,
                bill_no=f"TMP-{transaction_id}", created_by=user,
            )
            products = lock_products(store, [i["product_id"] for i in items])
            subtotal = tax_total = grand_total = 0
            for line in sorted(items, key=lambda i: i["product_id"]):
                product = products.get(line["product_id"])
                if product is None:
                    raise BusinessValidationError("Unknown product.", {"product_id": line["product_id"]})
                if not product.is_active:
                    raise BusinessValidationError("Product is inactive.", {"product_id": product.id})
                qty = line["quantity"]
                if product.stock_qty < qty:
                    raise InsufficientStock(
                        f"Only {product.stock_qty} unit(s) of '{product.name}' available.",
                        {"product_id": product.id, "available": product.stock_qty, "requested": qty},
                    )
                rate, approval = _resolve_rate(store, product, line.get("override_approval_id"))
                m = split_inclusive_line(rate, qty, product.gst_rate)
                item = SaleItem.objects.create(
                    sale=sale, product=product, quantity=qty, mrp_snapshot=product.mrp,
                    rate_applied=rate, gst_rate_snapshot=product.gst_rate,
                    taxable_value=m["taxable_value"], cgst=m["cgst"], sgst=m["sgst"],
                    line_total=m["line_total"], override_approval=approval,
                )
                apply_stock_change(
                    product=product, delta=-qty, movement_type=StockMovement.Type.SALE,
                    user=user, reference_type="SALE", reference_id=sale.id,
                    transaction_ref=str(transaction_id),
                )
                if approval:
                    approval.used_at = timezone.now()
                    approval.used_in_sale_item = item
                    approval.save(update_fields=["used_at", "used_in_sale_item"])
                subtotal += m["taxable_value"]
                tax_total += m["cgst"] + m["sgst"]
                grand_total += m["line_total"]
            sale.subtotal, sale.tax_total, sale.grand_total = subtotal, tax_total, grand_total
            sale.bill_no = f"S-{timezone.now().year}-{sale.id:06d}"
            sale.save(update_fields=["subtotal", "tax_total", "grand_total", "bill_no"])
            return sale, True
    except IntegrityError:
        if (sale := existing()):
            return resolve(sale)
        raise
