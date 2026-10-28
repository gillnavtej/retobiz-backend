from rest_framework.routers import DefaultRouter

from .views import PriceOverrideViewSet, SaleViewSet

router = DefaultRouter()
router.register("sales", SaleViewSet, basename="sale")
router.register("price-overrides", PriceOverrideViewSet, basename="price-override")
urlpatterns = router.urls
