import uuid
from decimal import Decimal as D

from django.core.management.base import BaseCommand
from django.db import transaction

from accounts.models import User
from catalog.models import Product, Store
from inventory.services import adjust_stock
from purchasing.models import Supplier
from purchasing.services import create_purchase
from sales.services import create_sale, issue_override

PRODUCTS = [  # name, mrp, purchase, selling, gst
    ("Parle-G 100g", "10.00", "7.50", "9.50", "18"), ("Amul Butter 100g", "56.00", "48.00", "54.00", "12"),
    ("Tata Salt 1kg", "28.00", "22.00", "26.00", "0"), ("Maggi Noodles 70g", "14.00", "11.00", "13.00", "12"),
    ("Aashirvaad Atta 5kg", "270.00", "235.00", "260.00", "5"), ("Coca-Cola 750ml", "40.00", "32.00", "38.00", "28"),
    ("Dettol Soap 75g", "45.00", "36.00", "42.00", "18"), ("Colgate 100g", "55.00", "44.00", "52.00", "18"),
    ("Surf Excel 1kg", "130.00", "105.00", "125.00", "18"), ("Britannia Bread", "45.00", "36.00", "42.00", "5"),
    ("Milk 500ml", "30.00", "27.00", "29.00", "0"), ("Eggs (6)", "48.00", "40.00", "46.00", "0"),
    ("Basmati Rice 1kg", "120.00", "95.00", "115.00", "5"), ("Sunflower Oil 1L", "160.00", "135.00", "150.00", "5"),
    ("Tea Powder 250g", "130.00", "105.00", "125.00", "5"), ("Sugar 1kg", "50.00", "42.00", "48.00", "5"),
    ("Pepsi 600ml", "40.00", "32.00", "38.00", "28"), ("Lays Chips 52g", "20.00", "15.00", "19.00", "12"),
    ("Dairy Milk 50g", "50.00", "40.00", "48.00", "18"), ("Notebook A5", "60.00", "45.00", "55.00", "12"),
]


class Command(BaseCommand):
    help = "Create demo store, users, products, purchases, sales, an adjustment and an override."

    @transaction.atomic
    def handle(self, *args, **opts):
        if Store.objects.filter(code="DEMO").exists():
            self.stdout.write("Demo data already present; nothing to do.")
            return
        store = Store.objects.create(name="Demo Mart", code="DEMO", state_code="27")
        admin = User.objects.create_user("admin", password="Admin@12345", store=store, role="ADMIN")
        cashier = User.objects.create_user("cashier", password="Cashier@12345", store=store, role="CASHIER")
        suppliers = [Supplier.objects.create(store=store, name=n, phone="9000000000")
                     for n in ("Fresh Foods Ltd", "City Wholesale", "Daily Needs Co")]
        products = [
            Product.objects.create(
                store=store, name=n, barcode=f"89017191{i:05d}", mrp=D(m), purchase_rate=D(p),
                selling_rate=D(s), gst_rate=D(g),
            ) for i, (n, m, p, s, g) in enumerate(PRODUCTS, start=1)
        ]
        half = len(products) // 2
        for ref, supplier, chunk in (("PUR-DEMO-1", suppliers[0], products[:half]),
                                     ("PUR-DEMO-2", suppliers[1], products[half:])):
            create_purchase(
                store=store, user=admin, reference=ref, supplier_id=supplier.id,
                items=[{"product_id": p.id, "quantity": 50, "purchase_rate": p.purchase_rate} for p in chunk],
            )
        for n in range(5):
            create_sale(
                store=store, user=cashier, transaction_id=uuid.uuid4(),
                items=[{"product_id": products[n].id, "quantity": 2},
                       {"product_id": products[n + 5].id, "quantity": 1}],
            )
        adjust_stock(store=store, user=admin, product_id=products[0].id, quantity_delta=-3,
                     reason="Expired stock", reference="ADJ-DEMO-1")
        approval = issue_override(store=store, admin_user=admin, product_id=products[2].id,
                                  requested_rate=D("23.00"), reason="Damaged pack")
        self.stdout.write(self.style.SUCCESS(
            f"Demo data created. Unused override approval id={approval.id} (product {products[2].id}, rate 23.00)."))
