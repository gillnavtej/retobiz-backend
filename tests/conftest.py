from decimal import Decimal as D
from itertools import count

import pytest
from rest_framework.test import APIClient

from accounts.models import User
from catalog.models import Product, Store

_barcode = count(1)


def make_store(code="S1"):
    return Store.objects.create(name=f"Store {code}", code=code, state_code="27")


def make_user(store, role, username=None):
    username = username or f"{role.lower()}_{store.code}"
    return User.objects.create_user(username, password="pw", store=store, role=role)


def make_product(store, stock=0, mrp="100.00", selling="100.00", gst="18", name=None):
    """Creates a product with a given opening stock via the ledger so invariants hold."""
    p = Product.objects.create(
        store=store, name=name or f"P{next(_barcode)}", barcode=f"B{next(_barcode):06d}",
        mrp=D(mrp), purchase_rate=D("50.00"), selling_rate=D(selling), gst_rate=D(gst),
    )
    if stock:
        from inventory.services import adjust_stock

        adjust_stock(store=store, user=make_user_cached(store, "ADMIN"), product_id=p.id,
                     quantity_delta=stock, reason="opening stock")
        p.refresh_from_db()
    return p


def make_user_cached(store, role):
    username = f"{role.lower()}_{store.code}"
    return User.objects.filter(username=username).first() or make_user(store, role)


def client_for(user):
    c = APIClient()
    c.force_authenticate(user)
    return c


@pytest.fixture
def store(db):
    return make_store("S1")


@pytest.fixture
def other_store(db):
    return make_store("S2")


@pytest.fixture
def admin(store):
    return make_user_cached(store, "ADMIN")


@pytest.fixture
def cashier(store):
    return make_user_cached(store, "CASHIER")


@pytest.fixture
def admin_client(admin):
    return client_for(admin)


@pytest.fixture
def cashier_client(cashier):
    return client_for(cashier)
