import pytest
from django.db import IntegrityError, transaction

from catalog.models import Product
from tests.conftest import client_for, make_product, make_store, make_user

BODY = {"name": "Biscuit", "barcode": "123", "mrp": "10.00", "purchase_rate": "7.00",
        "selling_rate": "9.50", "gst_rate": "18.00"}


def test_admin_creates_product(admin_client):
    r = admin_client.post("/api/v1/products/", BODY, format="json")
    assert r.status_code == 201 and r.json()["stock_qty"] == 0


def test_p01_duplicate_barcode_in_store(admin_client):
    admin_client.post("/api/v1/products/", BODY, format="json")
    r = admin_client.post("/api/v1/products/", BODY, format="json")
    assert r.status_code == 409 and r.json()["error"]["code"] == "DUPLICATE_BARCODE"


def test_p02_same_barcode_other_store_allowed(admin_client, other_store):
    admin_client.post("/api/v1/products/", BODY, format="json")
    other_admin = make_user(other_store, "ADMIN")
    assert client_for(other_admin).post("/api/v1/products/", BODY, format="json").status_code == 201


def test_p03_selling_rate_above_mrp(admin_client):
    r = admin_client.post("/api/v1/products/", {**BODY, "selling_rate": "11.00"}, format="json")
    assert r.status_code == 400 and r.json()["error"]["code"] == "VALIDATION_ERROR"


def test_a01_cashier_cannot_patch(cashier_client, store):
    p = make_product(store)
    r = cashier_client.patch(f"/api/v1/products/{p.id}/", {"selling_rate": "1.00"}, format="json")
    assert r.status_code == 403 and r.json()["error"]["code"] == "PERMISSION_DENIED"


def test_a02_cashier_cannot_create(cashier_client):
    assert cashier_client.post("/api/v1/products/", BODY, format="json").status_code == 403


def test_cashier_can_read_and_lookup_barcode(cashier_client, store):
    p = make_product(store)
    assert cashier_client.get(f"/api/v1/products/{p.id}/").status_code == 200
    assert cashier_client.get(f"/api/v1/products/by-barcode/{p.barcode}/").status_code == 200


def test_a06_cross_store_read_is_404(store, other_store):
    p = make_product(other_store)
    c = client_for(make_user(store, "CASHIER", "x"))
    assert c.get(f"/api/v1/products/{p.id}/").status_code == 404


def test_cashier_cannot_use_admin_endpoints(cashier_client):
    for path in ("/api/v1/stock-movements/", "/api/v1/purchases/", "/api/v1/price-overrides/"):
        assert cashier_client.get(path).status_code == 403


def test_unauthenticated_is_401(db):
    from rest_framework.test import APIClient

    r = APIClient().get("/api/v1/products/")
    assert r.status_code == 401 and r.json()["error"]["code"] == "AUTHENTICATION_FAILED"


@pytest.mark.django_db(transaction=True)
def test_db01_negative_stock_rejected_by_check_constraint(store):
    p = make_product(store, stock=1)
    with pytest.raises(IntegrityError), transaction.atomic():
        Product.objects.filter(pk=p.pk).update(stock_qty=-1)


@pytest.mark.django_db(transaction=True)
def test_db_selling_above_mrp_rejected_by_constraint(store):
    p = make_product(store)
    with pytest.raises(IntegrityError), transaction.atomic():
        Product.objects.filter(pk=p.pk).update(selling_rate=p.mrp + 1)
