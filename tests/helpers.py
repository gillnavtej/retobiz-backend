from django.db.models import Sum

from catalog.models import Product


def assert_ledger_matches_stock():
    """Invariant: per product, sum(quantity_delta) == stock_qty."""
    for p in Product.objects.annotate(ledger=Sum("movements__quantity_delta")):
        assert p.stock_qty == (p.ledger or 0), f"product {p.id}: stock {p.stock_qty} != ledger {p.ledger}"
