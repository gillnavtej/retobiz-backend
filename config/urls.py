from django.contrib import admin
from django.http import JsonResponse
from django.urls import include, path
from accounts.views import DashboardSummaryView
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView


def healthz(request):
    return JsonResponse({"status": "ok"})


urlpatterns = [
    path("admin/", admin.site.urls),
    path("healthz/", healthz),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema")),
    path("api/v1/dashboard/summary/", DashboardSummaryView.as_view()),
    path("api/v1/auth/", include("accounts.urls")),
    path("api/v1/", include("catalog.urls")),
    path("api/v1/", include("purchasing.urls")),
    path("api/v1/", include("sales.urls")),
    path("api/v1/", include("inventory.urls")),
]
