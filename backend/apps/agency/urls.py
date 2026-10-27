from django.urls import path, re_path

from . import manager_views as mv
from . import portal_views as v

urlpatterns = [
    path("portal/login/", v.PortalLoginView.as_view(), name="agency-portal-login"),
    path("portal/logout/", v.PortalLogoutView.as_view(), name="agency-portal-logout"),
    path("portal/me/", v.PortalMeView.as_view(), name="agency-portal-me"),
    path("portal/statement/", v.PortalStatementView.as_view(), name="agency-portal-statement"),
    # group managers (apps/agency/managers.py)
    path("manager/login/", mv.ManagerLoginGoneView.as_view(), name="agency-manager-login"),
    path("manager/logout/", mv.ManagerLoginGoneView.as_view(), name="agency-manager-logout"),
    path("manager/me/", mv.ManagerMeView.as_view(), name="agency-manager-me"),
    path("manager/admins/", mv.ManagerAdminCreateView.as_view(), name="agency-manager-admin-create"),
    path("manager/admins/<str:username>/statement/", mv.ManagerAdminStatementView.as_view(), name="agency-manager-statement"),
    path("manager/admins/<str:username>/<str:action>/", mv.ManagerAdminActionView.as_view(), name="agency-manager-admin-action"),
    path("manager/accounting/", mv.ManagerAccountingView.as_view(), name="agency-manager-accounting"),
    path("manager/groups/<int:group_id>/statement/", mv.ManagerGroupStatementView.as_view(), name="agency-manager-group-statement"),
    path("manager/activity/", mv.ManagerActivityView.as_view(), name="agency-manager-activity"),
    re_path(r"^manager/.*$", mv.ManagerForbiddenView.as_view(), name="agency-manager-forbidden"),
]
