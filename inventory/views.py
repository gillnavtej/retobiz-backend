from django.utils.dateparse import parse_date
from rest_framework import viewsets
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import IsAdminRole

from .models import StockMovement
from .serializers import StockAdjustmentInputSerializer, StockMovementSerializer
from .services import adjust_stock


class StockMovementViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = StockMovementSerializer
    permission_classes = [IsAdminRole]

    def get_queryset(self):
        qs = StockMovement.objects.filter(store=self.request.user.store).select_related("created_by")
        p = self.request.query_params
        if p.get("product"):
            qs = qs.filter(product_id=p["product"])
        if p.get("type"):
            qs = qs.filter(movement_type=p["type"].upper())
        if p.get("transaction_ref"):
            qs = qs.filter(transaction_ref=p["transaction_ref"])
        if p.get("from") and (d := parse_date(p["from"])):
            qs = qs.filter(created_at__date__gte=d)
        if p.get("to") and (d := parse_date(p["to"])):
            qs = qs.filter(created_at__date__lte=d)
        return qs.order_by("-id")


class StockAdjustmentView(APIView):
    permission_classes = [IsAdminRole]

    def post(self, request):
        s = StockAdjustmentInputSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        d = s.validated_data
        movement, created = adjust_stock(
            store=request.user.store, user=request.user, product_id=d["product_id"],
            quantity_delta=d["quantity_delta"], reason=d["reason"], reference=d["reference"],
        )
        return Response(StockMovementSerializer(movement).data, status=201 if created else 200)
