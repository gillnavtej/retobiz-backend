from django.conf import settings
from django.db import IntegrityError
from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework import viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from accounts.permissions import IsAdminOrReadOnlyForCashier
from common.exceptions import DuplicateBarcode

from .models import Product
from .serializers import ProductSerializer


class ProductViewSet(viewsets.ModelViewSet):
    serializer_class = ProductSerializer
    permission_classes = [IsAdminOrReadOnlyForCashier]
    http_method_names = ["get", "post", "put", "patch", "head", "options"]

    def get_queryset(self):
        qs = Product.objects.filter(store=self.request.user.store).order_by("id")
        p = self.request.query_params
        if p.get("search"):
            qs = qs.filter(Q(name__icontains=p["search"]) | Q(barcode__icontains=p["search"]))
        if p.get("barcode"):
            qs = qs.filter(barcode=p["barcode"])
        if p.get("is_active") in ("true", "false"):
            qs = qs.filter(is_active=p["is_active"] == "true")
        if p.get("low_stock") == "true":
            qs = qs.filter(stock_qty__lte=settings.LOW_STOCK_THRESHOLD, is_active=True)
        return qs

    def _save(self, serializer, creating):
        try:
            if creating:
                serializer.save(store=self.request.user.store)
            else:
                serializer.save()
        except IntegrityError as exc:  # parallel duplicate that slipped past validation
            if "uniq_product_store_barcode" in str(exc):
                raise DuplicateBarcode() from exc
            raise

    def perform_create(self, serializer):
        self._save(serializer, True)

    def perform_update(self, serializer):
        self._save(serializer, False)

    @action(detail=False, methods=["get"], url_path=r"by-barcode/(?P<barcode>[^/]+)")
    def by_barcode(self, request, barcode=None):
        product = get_object_or_404(self.get_queryset(), barcode=barcode)
        return Response(self.get_serializer(product).data)
