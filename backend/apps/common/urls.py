from django.urls import path

from .views import ApiRootView, HealthView

app_name = "common"

urlpatterns = [
    path("", ApiRootView.as_view(), name="root"),
    path("health/", HealthView.as_view(), name="health"),
]
