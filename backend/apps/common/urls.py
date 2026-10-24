from django.urls import path

from .views import ApiRootView, DomainProbeView, HealthView

app_name = "common"

urlpatterns = [
    path("", ApiRootView.as_view(), name="root"),
    path("health/", HealthView.as_view(), name="health"),
    path("domain-probe/<str:nonce>/", DomainProbeView.as_view(), name="domain-probe"),
]
