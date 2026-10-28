from rest_framework import mixins, viewsets
from rest_framework.response import Response

from accounts.permissions import IsAdminRole

from .models import Purchase, Supplier
from .serializers import PurchaseInputSerializer, PurchaseSerializer, SupplierSerializer
from .services import create_purchase


class SupplierViewSet(viewsets.ModelViewSet):
    serializer_class = SupplierSerializer
    permission_classes = [IsAdminRole]
    http_method_names = ["get", "post", "put", "patch", "head", "options"]

    def get_queryset(self):
        return Supplier.objects.filter(store=self.request.user.store).order_by("id")

    def perform_create(self, serializer):
        serializer.save(store=self.request.user.store)


class PurchaseViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    serializer_class = PurchaseSerializer
    permission_classes = [IsAdminRole]

    def get_queryset(self):
        return (
            Purchase.objects.filter(store=self.request.user.store)
            .prefetch_related("items").order_by("-id")
        )

    def create(self, request):
        s = PurchaseInputSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        purchase, created = create_purchase(
            store=request.user.store, user=request.user, reference=d["reference"],
            supplier_id=d["supplier_id"], items=d["items"],
        )
        purchase = Purchase.objects.prefetch_related("items").get(pk=purchase.pk)
        return Response(PurchaseSerializer(purchase).data, status=201 if created else 200)
