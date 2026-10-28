"""Failures mid-transaction must leave no partial updates."""
from unittest import mock
from uuid import uuid4

import pytest

from catalog.models import Product
from common.exceptions import BusinessValidationError
from inventory.models import StockMovement
from purchasing.models import Purchase, Supplier
from purchasing.services import create_purchase
from sales.models import PriceOverrideApproval, Sale, SaleItem
from sales.services import create_sale
from tests.conftest import make_product, make_user_cached
from tests.helpers import assert_ledger_matches_stock

pytestmark = pytest.mark.django_db(transaction=True)


def _sale_args(store, user, *products):
    return dict(store=store, user=user, transaction_id=uuid4(),
                items=[{"product_id": p.id, "quantity": 1} for p in products])


def test_f01_ledger_failure_rolls_back_everything(store, cashier):
    a, b = make_product(store, stock=5), make_product(store, stock=5)
    before = StockMovement.objects.count()
    with mock.patch("inventory.services.StockMovement.objects.create", side_effect=RuntimeError("boom")):
        with pytest.raises(RuntimeError):
            create_sale(**_sale_args(store, cashier, a, b))
    a.refresh_from_db(); b.refresh_from_db()
    assert (a.stock_qty, b.stock_qty) == (5, 5)
    assert Sale.objects.count() == 0 and SaleItem.objects.count() == 0
    assert StockMovement.objects.count() == before
    assert_ledger_matches_stock()


def test_f03_failure_after_stock_update_before_commit(store, cashier):
    a, b = make_product(store, stock=5), make_product(store, stock=5)
    real = Product.save
    calls = {"n": 0}

    def flaky_save(self, *args, **kwargs):
        real(self, *args, **kwargs)
        calls["n"] += 1
        if calls["n"] == 2:  # fail after the second product's stock row was updated
            raise RuntimeError("crash before commit")

    with mock.patch.object(Product, "save", flaky_save):
        with pytest.raises(RuntimeError):
            create_sale(**_sale_args(store, cashier, a, b))
    a.refresh_from_db(); b.refresh_from_db()
    assert (a.stock_qty, b.stock_qty) == (5, 5)
    assert Sale.objects.count() == 0
    assert_ledger_matches_stock()


def test_failed_sale_does_not_consume_override_or_txn_id(store, cashier, admin):
    from sales.services import issue_override

    p = make_product(store, stock=1, mrp="100.00", selling="100.00")
    approval = issue_override(store=store, admin_user=admin, product_id=p.id,
                              requested_rate=100 - 10, reason="x")
    tid = uuid4()
    with pytest.raises(Exception):
        create_sale(store=store, user=cashier, transaction_id=tid, items=[
            {"product_id": p.id, "quantity": 5, "override_approval_id": approval.id}])
    approval.refresh_from_db()
    assert approval.used_at is None
    # the same transaction id is still usable for a corrected request
    sale, created = create_sale(store=store, user=cashier, transaction_id=tid, items=[
        {"product_id": p.id, "quantity": 1, "override_approval_id": approval.id}])
    assert created and sale.grand_total == 90


def test_f04_purchase_fails_on_second_item_first_unchanged(store, admin):
    sup = Supplier.objects.create(store=store, name="S")
    p = make_product(store, stock=3)
    with pytest.raises(BusinessValidationError):
        create_purchase(store=store, user=admin, reference="PUR-X", supplier_id=sup.id, items=[
            {"product_id": p.id, "quantity": 10, "purchase_rate": "5.00"},
            {"product_id": 999999, "quantity": 1, "purchase_rate": "5.00"}])
    p.refresh_from_db()
    assert p.stock_qty == 3
    assert Purchase.objects.count() == 0
    assert_ledger_matches_stock()
