from django.core.management.base import BaseCommand
from django.db.models import Sum

from catalog.models import Product


class Command(BaseCommand):
    help = "Report products whose stock_qty differs from the sum of ledger deltas."

    def handle(self, *args, **opts):
        bad = 0
        for p in Product.objects.annotate(ledger=Sum("movements__quantity_delta")):
            if p.stock_qty != (p.ledger or 0):
                bad += 1
                self.stdout.write(self.style.ERROR(f"MISMATCH product={p.id} stock={p.stock_qty} ledger={p.ledger or 0}"))
        self.stdout.write(self.style.SUCCESS("Ledger OK") if not bad else f"{bad} mismatch(es)")
        if bad:
            raise SystemExit(1)
