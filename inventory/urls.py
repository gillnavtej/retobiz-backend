from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import StockAdjustmentView, StockMovementViewSet

router = DefaultRouter()
router.register("stock-movements", StockMovementViewSet, basename="stock-movement")
urlpatterns = [path("stock-adjustments/", StockAdjustmentView.as_view())] + router.urls
