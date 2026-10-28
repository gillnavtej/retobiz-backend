from django.contrib import admin

from .models import PriceOverrideApproval, Sale, SaleItem

admin.site.register(Sale)
admin.site.register(SaleItem)
admin.site.register(PriceOverrideApproval)
