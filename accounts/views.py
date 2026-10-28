from datetime import timedelta

from django.conf import settings
from django.db.models import Count, Sum
from django.utils import timezone
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.views import TokenObtainPairView

from catalog.models import Product
from sales.models import Sale

from .permissions import IsAdminRole
from .serializers import LoginSerializer, MeSerializer


class LoginView(TokenObtainPairView):
    serializer_class = LoginSerializer
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "login"


class MeView(APIView):
    def get(self, request):
        return Response(MeSerializer(request.user).data)


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            RefreshToken(request.data.get("refresh", "")).blacklist()
        except TokenError:
            return Response(
                {"error": {"code": "VALIDATION_ERROR", "message": "Invalid refresh token.", "details": {}}},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(status=status.HTTP_204_NO_CONTENT)


class DashboardSummaryView(APIView):
    permission_classes = [IsAdminRole]

    def get(self, request):
        store = request.user.store
        start = timezone.localtime().replace(hour=0, minute=0, second=0, microsecond=0)
        agg = Sale.objects.filter(store=store, created_at__gte=start, created_at__lt=start + timedelta(days=1)).aggregate(
            total=Sum("grand_total"), bills=Count("id")
        )
        low = Product.objects.filter(
            store=store, is_active=True, stock_qty__lte=settings.LOW_STOCK_THRESHOLD
        ).count()
        return Response(
            {
                "today_sales_total": str(agg["total"] or "0.00"),
                "today_bill_count": agg["bills"],
                "low_stock_count": low,
            }
        )
