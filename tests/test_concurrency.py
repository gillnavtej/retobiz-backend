"""Real-commit concurrency tests. PostgreSQL only (SQLite ignores row locks)."""
import threading
from uuid import uuid4

import pytest
from django.db import connection

from catalog.models import Product
from inventory.models import StockMovement
from purchasing.models import Supplier
from sales.models import Sale
from tests.conftest import client_for, make_product, make_store, make_user
from tests.helpers import assert_ledger_matches_stock

pytestmark = pytest.mark.django_db(transaction=True)


def run_parallel(n, fn):
    """Run fn(i) in n threads released together; returns results in order."""
    barrier = threading.Barrier(n)
    results = [None] * n

    def worker(i):
        try:
            barrier.wait()
            results[i] = fn(i)
        except Exception as exc:  # surface failures in the assertion, not a silent thread death
            results[i] = exc
        finally:
            connection.close()

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(n)]
    [t.start() for t in threads]
    [t.join() for t in threads]
    return results


def post_sale(user, items, tid=None):
    return client_for(user).post(
        "/api/v1/sales/", {"transaction_id": str(tid or uuid4()), "items": items}, format="json")


@pytest.fixture
def setup():
    store = make_store("CC")
    return store, make_user(store, "CASHIER", "cc_cashier"), make_user(store, "ADMIN", "cc_admin")


def test_c01_last_unit_only_one_succeeds(setup):
    store, cashier, _ = setup
    p = make_product(store, stock=1)
    res = run_parallel(2, lambda i: post_sale(cashier, [{"product_id": p.id, "quantity": 1}]))
    assert sorted(r.status_code for r in res) == [201, 409]
    p.refresh_from_db()
    assert p.stock_qty == 0
    assert_ledger_matches_stock()


def test_c02_ten_threads_five_units(setup):
    store, cashier, _ = setup
    p = make_product(store, stock=5)
    res = run_parallel(10, lambda i: post_sale(cashier, [{"product_id": p.id, "quantity": 1}]))
    codes = [r.status_code for r in res]
    assert codes.count(201) == 5 and codes.count(409) == 5
    p.refresh_from_db()
    assert p.stock_qty == 0
    assert StockMovement.objects.filter(movement_type="SALE").count() == 5
    assert_ledger_matches_stock()


def test_c03_opposite_order_multi_item_no_deadlock(setup):
    store, cashier, _ = setup
    a, b = make_product(store, stock=20), make_product(store, stock=20)
    orders = [[a, b], [b, a]]
    res = run_parallel(
        8, lambda i: post_sale(cashier, [{"product_id": p.id, "quantity": 1} for p in orders[i % 2]]))
    assert all(r.status_code == 201 for r in res), [getattr(r, "content", r) for r in res]
    a.refresh_from_db(); b.refresh_from_db()
    assert (a.stock_qty, b.stock_qty) == (12, 12)
    assert_ledger_matches_stock()


def test_c04_concurrent_purchases_no_lost_update(setup):
    store, _, admin = setup
    p = make_product(store, stock=0)
    sup = Supplier.objects.create(store=store, name="S")

    def buy(i):
        return client_for(admin).post("/api/v1/purchases/", {
            "reference": f"PUR-{i}", "supplier_id": sup.id,
            "items": [{"product_id": p.id, "quantity": 10, "purchase_rate": "5.00"}]}, format="json")

    res = run_parallel(6, buy)
    assert all(r.status_code == 201 for r in res)
    p.refresh_from_db()
    assert p.stock_qty == 60
    assert_ledger_matches_stock()


def test_d02_identical_requests_simultaneously_one_sale(setup):
    store, cashier, _ = setup
    p = make_product(store, stock=10)
    tid = uuid4()
    res = run_parallel(5, lambda i: post_sale(cashier, [{"product_id": p.id, "quantity": 2}], tid))
    assert sorted(r.status_code for r in res) == [200, 200, 200, 200, 201]
    assert len({r.json()["id"] for r in res}) == 1
    p.refresh_from_db()
    assert p.stock_qty == 8 and Sale.objects.count() == 1
    assert_ledger_matches_stock()


def test_d02b_identical_requests_on_last_unit_still_one_sale(setup):
    """Replays must resolve to the original sale even if the stock is now exhausted."""
    store, cashier, _ = setup
    p = make_product(store, stock=1)
    tid = uuid4()
    res = run_parallel(4, lambda i: post_sale(cashier, [{"product_id": p.id, "quantity": 1}], tid))
    assert sorted(r.status_code for r in res) == [200, 200, 200, 201]
    p.refresh_from_db()
    assert p.stock_qty == 0
