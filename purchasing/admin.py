from django.contrib import admin

from .models import Purchase, PurchaseItem, Supplier

admin.site.register(Supplier)
admin.site.register(Purchase)
admin.site.register(PurchaseItem)
