from django.urls import path

from .views import (
    PublicActiveThemeView,
    PublicPageDetailView,
    PublicPageListView,
    PublicSiteConfigView,
)

app_name = "settings_app"

urlpatterns = [
    path("config/", PublicSiteConfigView.as_view(), name="config"),
    path("theme/", PublicActiveThemeView.as_view(), name="theme"),
    path("pages/", PublicPageListView.as_view(), name="pages"),
    path("pages/<slug:slug>/", PublicPageDetailView.as_view(), name="page-detail"),
]
