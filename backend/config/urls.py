from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)

api_v1 = [
    path("", include("apps.common.urls")),
    path("auth/", include("apps.accounts.urls")),
    path("plans/", include("apps.plans.urls")),
    path("orders/", include("apps.orders.urls")),
    path("payments/", include("apps.payments_sms.urls")),
    path("services/", include("apps.panel.urls")),
    path("", include("apps.settings_app.urls")),
    path("admin/", include("apps.adminpanel.urls")),
]

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/", include((api_v1, "api_v1"))),
    # OpenAPI schema + docs
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    path("api/redoc/", SpectacularRedocView.as_view(url_name="schema"), name="redoc"),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
