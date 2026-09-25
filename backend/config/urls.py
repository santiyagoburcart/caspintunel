from pathlib import Path

from django.conf import settings
from django.contrib import admin
from django.urls import include, path, re_path
from django.views.static import serve
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
    path("notifications/", include("apps.notifications.urls")),
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

# Public media = branding only (logo / favicon). Receipts and operator apps are
# private (served through auth-checked API views), so they are never exposed
# here. In prod nginx serves /media/branding/ itself; on the dev-compose server
# (DEBUG=False, nginx proxies /media/ to Django) this is what serves the logo.
def _branding_media(request, path):
    return serve(request, path, document_root=str(Path(settings.MEDIA_ROOT) / "branding"))


urlpatterns += [re_path(r"^media/branding/(?P<path>[^/]+)$", _branding_media)]
