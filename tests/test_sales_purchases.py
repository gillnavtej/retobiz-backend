from decimal import Decimal as D
from uuid import uuid4

from inventory.models import StockMovement
from sales.models import PriceOverrideApproval, Sale
from tests.conftest import client_for, make_product, make_store, make_user
from tests.helpers import assert_ledger_matches_stock


def sale_body(items, tid=None):
    return {"transaction_id": str(tid or uuid4()), "items": items}


def test_purchase_increases_stock_and_writes_ledger(admin_client, store, admin):
    from purchasing.models import Supplier

    sup = Supplier.objects.create(store=store, name="S")
    p = make_product(store)
    r = admin_client.post("/api/v1/purchases/", {
        "reference": "PUR-1", "supplier_id": sup.id,
        "items": [{"product_id": p.id, "quantity": 100, "purchase_rate": "7.40"}]}, format="json")
    assert r.status_code == 201 and r.json()["total_amount"] == "740.00"
    p.refresh_from_db()
    assert p.stock_qty == 100
    mv = StockMovement.objects.get(movement_type="PURCHASE")
    assert (mv.quantity_delta, mv.balance_after, mv.created_by_id, mv.transaction_ref) == (100, 100, admin.id, "PUR-1")
    assert_ledger_matches_stock()


def test_d04_duplicate_purchase_reference_no_double_stock(admin_client, store):
    from purchasing.models import Supplier

    sup = Supplier.objects.create(store=store, name="S")
    p = make_product(store)
    body = {"reference": "PUR-1", "supplier_id": sup.id,
            "items": [{"product_id": p.id, "quantity": 10, "purchase_rate": "5.00"}]}
    assert admin_client.post("/api/v1/purchases/", body, format="json").status_code == 201
    assert admin_client.post("/api/v1/purchases/", body, format="json").status_code == 200
    body["items"][0]["quantity"] = 11
    assert admin_client.post("/api/v1/purchases/", body, format="json").status_code == 409
    p.refresh_from_db()
    assert p.stock_qty == 10
    assert_ledger_matches_stock()


def test_sale_totals_and_ledger(cashier_client, store, cashier):
    p = make_product(store, stock=10, mrp="10.00", selling="9.50", gst="18")
    r = cashier_client.post("/api/v1/sales/", sale_body([{"product_id": p.id, "quantity": 2}]), format="json")
    assert r.status_code == 201
    b = r.json()
    assert (b["subtotal"], b["tax_total"], b["grand_total"]) == ("16.10", "2.90", "19.00")
    assert b["items"][0]["cgst"] == "1.45" and b["bill_no"].startswith("S-")
    p.refresh_from_db()
    assert p.stock_qty == 8
    mv = StockMovement.objects.filter(movement_type="SALE").get()
    assert (mv.quantity_delta, mv.balance_after, mv.created_by_id) == (-2, 8, cashier.id)
    assert_ledger_matches_stock()


def test_d01_replay_returns_original_and_stock_once(cashier_client, store):
    p = make_product(store, stock=10)
    body = sale_body([{"product_id": p.id, "quantity": 3}])
    r1 = cashier_client.post("/api/v1/sales/", body, format="json")
    r2 = cashier_client.post("/api/v1/sales/", body, format="json")
    assert (r1.status_code, r2.status_code) == (201, 200) and r1.json() == r2.json()
    p.refresh_from_db()
    assert p.stock_qty == 7 and Sale.objects.count() == 1
    assert StockMovement.objects.filter(movement_type="SALE").count() == 1


def test_d03_same_txn_different_items_conflict(cashier_client, store):
    p = make_product(store, stock=10)
    tid = uuid4()
    cashier_client.post("/api/v1/sales/", sale_body([{"product_id": p.id, "quantity": 1}], tid), format="json")
    r = cashier_client.post("/api/v1/sales/", sale_body([{"product_id": p.id, "quantity": 2}], tid), format="json")
    assert r.status_code == 409 and r.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"
    p.refresh_from_db()
    assert p.stock_qty == 9


def test_oversell_rejected(cashier_client, store):
    p = make_product(store, stock=1)
    r = cashier_client.post("/api/v1/sales/", sale_body([{"product_id": p.id, "quantity": 2}]), format="json")
    err = r.json()["error"]
    assert r.status_code == 409 and err["code"] == "INSUFFICIENT_STOCK"
    assert err["details"] == {"product_id": p.id, "available": 1, "requested": 2}
    assert Sale.objects.count() == 0


def test_f02_multi_line_failure_deducts_nothing(cashier_client, store):
    a, b, c = (make_product(store, stock=5), make_product(store, stock=5), make_product(store, stock=0))
    r = cashier_client.post("/api/v1/sales/", sale_body([
        {"product_id": a.id, "quantity": 1}, {"product_id": b.id, "quantity": 1},
        {"product_id": c.id, "quantity": 1}]), format="json")
    assert r.status_code == 409
    a.refresh_from_db(); b.refresh_from_db()
    assert (a.stock_qty, b.stock_qty) == (5, 5)
    assert Sale.objects.count() == 0
    assert_ledger_matches_stock()


def test_a05_forged_rate_ignored(cashier_client, store):
    p = make_product(store, stock=5, selling="100.00")
    r = cashier_client.post("/api/v1/sales/", sale_body(
        [{"product_id": p.id, "quantity": 1, "rate_applied": "1.00", "selling_rate": "1.00"}]), format="json")
    assert r.status_code == 201 and r.json()["items"][0]["rate_applied"] == "100.00"


def test_a03_valid_override(admin_client, cashier_client, store):
    p = make_product(store, stock=5, mrp="100.00", selling="100.00", gst="0")
    ov = admin_client.post("/api/v1/price-overrides/", {
        "product_id": p.id, "requested_rate": "90.00", "reason": "Damaged"}, format="json")
    assert ov.status_code == 201 and ov.json()["original_rate"] == "100.00" and ov.json()["used"] is False
    r = cashier_client.post("/api/v1/sales/", sale_body(
        [{"product_id": p.id, "quantity": 1, "override_approval_id": ov.json()["id"]}]), format="json")
    assert r.status_code == 201 and r.json()["items"][0]["rate_applied"] == "90.00"
    a = PriceOverrideApproval.objects.get(pk=ov.json()["id"])
    assert a.used_at is not None and a.used_in_sale_item_id == r.json()["items"][0]["id"]


def test_a04_invalid_overrides(admin_client, cashier_client, store):
    p = make_product(store, stock=10, selling="100.00", mrp="100.00")
    q = make_product(store, stock=10, selling="100.00", mrp="100.00")
    ov = admin_client.post("/api/v1/price-overrides/", {
        "product_id": p.id, "requested_rate": "90.00", "reason": "x"}, format="json").json()["id"]

    def sell(pid, approval):
        return cashier_client.post("/api/v1/sales/", sale_body(
            [{"product_id": pid, "quantity": 1, "override_approval_id": approval}]), format="json")

    wrong_product = sell(q.id, ov)
    assert wrong_product.status_code == 422 and wrong_product.json()["error"]["code"] == "INVALID_OVERRIDE"
    assert sell(p.id, 99999).status_code == 422
    assert sell(p.id, ov).status_code == 201
    reused = sell(p.id, ov)  # new transaction id, same approval
    assert reused.status_code == 422
    p.refresh_from_db()
    assert p.stock_qty == 9
    # rate changed after approval -> approval invalid
    ov2 = admin_client.post("/api/v1/price-overrides/", {
        "product_id": q.id, "requested_rate": "90.00", "reason": "x"}, format="json").json()["id"]
    admin_client.patch(f"/api/v1/products/{q.id}/", {"selling_rate": "95.00"}, format="json")
    assert sell(q.id, ov2).status_code == 422


def test_override_limits_and_admin_only(admin_client, cashier_client, store):
    p = make_product(store, selling="100.00", mrp="100.00")
    body = {"product_id": p.id, "requested_rate": "50.00", "reason": "x"}
    assert admin_client.post("/api/v1/price-overrides/", body, format="json").status_code == 400  # >20% off
    assert cashier_client.post("/api/v1/price-overrides/", {**body, "requested_rate": "90.00"}, format="json").status_code == 403


def test_cashier_sees_only_own_sales_and_txn_lookup(store, cashier, admin):
    p = make_product(store, stock=10)
    other_cashier = make_user(store, "CASHIER", "c2")
    tid = uuid4()
    client_for(cashier).post("/api/v1/sales/", sale_body([{"product_id": p.id, "quantity": 1}], tid), format="json")
    client_for(other_cashier).post("/api/v1/sales/", sale_body([{"product_id": p.id, "quantity": 1}]), format="json")
    assert client_for(cashier).get("/api/v1/sales/").json()["count"] == 1
    assert client_for(admin).get("/api/v1/sales/").json()["count"] == 2
    assert client_for(admin).get(f"/api/v1/sales/?transaction_id={tid}").json()["count"] == 1


def test_adjustment_rules(admin_client, cashier_client, store):
    p = make_product(store, stock=5)
    body = {"product_id": p.id, "quantity_delta": -3, "reason": "Expired", "reference": "ADJ-1"}
    assert cashier_client.post("/api/v1/stock-adjustments/", body, format="json").status_code == 403
    assert admin_client.post("/api/v1/stock-adjustments/", body, format="json").status_code == 201
    assert admin_client.post("/api/v1/stock-adjustments/", body, format="json").status_code == 200  # replay
    p.refresh_from_db()
    assert p.stock_qty == 2
    r = admin_client.post("/api/v1/stock-adjustments/", {**body, "quantity_delta": -9, "reference": "ADJ-2"}, format="json")
    assert r.status_code == 409 and r.json()["error"]["code"] == "INSUFFICIENT_STOCK"
    assert admin_client.post("/api/v1/stock-adjustments/", {**body, "quantity_delta": 0}, format="json").status_code == 400
    assert_ledger_matches_stock()


def test_l01_ledger_endpoint_and_append_only(admin_client, store):
    import pytest

    from inventory.models import AppendOnlyError

    p = make_product(store, stock=5)
    r = admin_client.get(f"/api/v1/stock-movements/?product={p.id}&type=ADJUSTMENT")
    assert r.status_code == 200 and r.json()["count"] == 1
    mv = StockMovement.objects.first()
    mv.reason = "tamper"
    with pytest.raises(AppendOnlyError):
        mv.save()
    with pytest.raises(AppendOnlyError):
        mv.delete()
    with pytest.raises(AppendOnlyError):
        StockMovement.objects.all().update(reason="x")
