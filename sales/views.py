import uuid

from rest_framework import mixins, viewsets
from rest_framework.response import Response

from accounts.permissions import HasStore, IsAdminRole

from .models import PriceOverrideApproval, Sale
from .serializers import (
    PriceOverrideInputSerializer, PriceOverrideSerializer, SaleInputSerializer, SaleSerializer,
)
from .services import create_sale, issue_override


class SaleViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    serializer_class = SaleSerializer
    permission_classes = [HasStore]

    def get_queryset(self):
        u = self.request.user
        qs = Sale.objects.filter(store=u.store).select_related("created_by").prefetch_related("items")
        if u.role != "ADMIN":
            qs = qs.filter(created_by=u)  # cashiers see only their own bills
        tid = self.request.query_params.get("transaction_id")
        if tid:
            try:
                qs = qs.filter(transaction_id=uuid.UUID(tid))
            except ValueError:
                return qs.none()
        return qs.order_by("-id")

    def create(self, request):
        s = SaleInputSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        sale, created = create_sale(
            store=request.user.store, user=request.user,
            transaction_id=d["transaction_id"], items=d["items"],
        )
        sale = self.get_queryset().model.objects.select_related("created_by").prefetch_related("items").get(pk=sale.pk)
        return Response(SaleSerializer(sale).data, status=201 if created else 200)


class PriceOverrideViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    serializer_class = PriceOverrideSerializer
    permission_classes = [IsAdminRole]

    def get_queryset(self):
        return PriceOverrideApproval.objects.filter(store=self.request.user.store).select_related("approved_by").order_by("-id")

    def create(self, request):
        s = PriceOverrideInputSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        approval = issue_override(
            store=request.user.store, admin_user=request.user, product_id=d["product_id"],
            requested_rate=d["requested_rate"], reason=d["reason"],
        )
        return Response(PriceOverrideSerializer(approval).data, status=201)
