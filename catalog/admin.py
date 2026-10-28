from django.contrib import admin

from .models import Product, Store

admin.site.register(Store)
admin.site.register(Product)
