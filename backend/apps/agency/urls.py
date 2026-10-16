from django.urls import path

from . import portal_views as v

urlpatterns = [
    path("portal/login/", v.PortalLoginView.as_view(), name="agency-portal-login"),
    path("portal/logout/", v.PortalLogoutView.as_view(), name="agency-portal-logout"),
    path("portal/me/", v.PortalMeView.as_view(), name="agency-portal-me"),
    path("portal/statement/", v.PortalStatementView.as_view(), name="agency-portal-statement"),
]
