from django.urls import path, re_path

from . import billing_views as bv
from . import manager_views as mv
from . import portal_views as v

urlpatterns = [
    path("portal/login/", v.PortalLoginView.as_view(), name="agency-portal-login"),
    path("portal/logout/", v.PortalLogoutView.as_view(), name="agency-portal-logout"),
    path("portal/me/", v.PortalMeView.as_view(), name="agency-portal-me"),
    path("portal/statement/", v.PortalStatementView.as_view(), name="agency-portal-statement"),
    path("portal/history/", v.PortalHistoryView.as_view(), name="agency-portal-history"),              # v1.54 «تاریخچه»
    # v1.34 invoices / requests / payments (billing_views.py)
    path("portal/invoices/", bv.PortalInvoicesView.as_view(), name="agency-portal-invoices"),
    path("portal/requests/", bv.PortalRequestsView.as_view(), name="agency-portal-requests"),
    path("portal/requests/quote/", bv.PortalRequestQuoteView.as_view(), name="agency-portal-request-quote"),
    path("portal/payments/", bv.PortalPaymentsView.as_view(), name="agency-portal-payments"),
    path("portal/payments/all/", bv.PortalPayAllView.as_view(), name="agency-portal-pay-all"),
    path("portal/payments/<int:pk>/", bv.PortalPaymentView.as_view(), name="agency-portal-payment"),
    path("portal/payments/<int:pk>/<str:action>/", bv.PortalPaymentView.as_view(), name="agency-portal-payment-action"),
    path("portal/notices/", bv.PortalNoticesView.as_view(), name="agency-portal-notices"),
    path("portal/debt/", bv.PortalDebtView.as_view(), name="agency-portal-debt"),
    path("portal/invoices/settlement/", bv.PortalSettlementView.as_view(), name="agency-portal-settlement"),
    path("portal/push/", bv.PortalPushView.as_view(), name="agency-portal-push"),
    path("portal/push/<str:action>/", bv.PortalPushView.as_view(), name="agency-portal-push-action"),
    # group managers (apps/agency/managers.py)
    path("manager/login/", mv.ManagerLoginGoneView.as_view(), name="agency-manager-login"),
    path("manager/logout/", mv.ManagerLoginGoneView.as_view(), name="agency-manager-logout"),
    path("manager/me/", mv.ManagerMeView.as_view(), name="agency-manager-me"),
    path("manager/admins/", mv.ManagerAdminCreateView.as_view(), name="agency-manager-admin-create"),
    path("manager/admins/live/", mv.ManagerAdminsLiveView.as_view(), name="agency-manager-admins-live"),
    path("manager/admins/<str:username>/stats/", mv.ManagerAdminStatsView.as_view(), name="agency-manager-admin-stats"),
    path("manager/admins/<str:username>/statement/", mv.ManagerAdminStatementView.as_view(), name="agency-manager-statement"),
    path("manager/admins/<str:username>/<str:action>/", mv.ManagerAdminActionView.as_view(), name="agency-manager-admin-action"),
    path("manager/accounting/", mv.ManagerAccountingView.as_view(), name="agency-manager-accounting"),
    path("manager/history/", mv.ManagerHistoryView.as_view(), name="agency-manager-history"),          # v1.54 «تاریخچه»
    path("manager/groups/<int:group_id>/statement/", mv.ManagerGroupStatementView.as_view(), name="agency-manager-group-statement"),
    path("manager/activity/", mv.ManagerActivityView.as_view(), name="agency-manager-activity"),
    path("manager/password/", mv.ManagerPasswordView.as_view(), name="agency-manager-password"),
    path("manager/invoices/", bv.ManagerInvoicesView.as_view(), name="agency-manager-invoices"),
    path("manager/invoices/settlement/", bv.ManagerSettlementView.as_view(), name="agency-manager-settlement"),
    path("manager/requests/", bv.ManagerRequestsView.as_view(), name="agency-manager-requests"),
    path("manager/debt/", bv.ManagerDebtView.as_view(), name="agency-manager-debt"),
    path("manager/payments/all/", bv.ManagerPayAllView.as_view(), name="agency-manager-pay-all"),
    path("manager/payments/", bv.ManagerPaymentsView.as_view(), name="agency-manager-payments"),
    path("manager/payments/<int:pk>/", bv.ManagerPaymentView.as_view(), name="agency-manager-payment"),
    path("manager/payments/<int:pk>/<str:action>/", bv.ManagerPaymentView.as_view(), name="agency-manager-payment-action"),
    path("manager/notices/", bv.ManagerNoticesView.as_view(), name="agency-manager-notices"),
    path("manager/prefs/", mv.ManagerPrefsView.as_view(), name="agency-manager-prefs"),
    path("manager/push/", mv.ManagerPushView.as_view(), name="agency-manager-push"),
    path("manager/push/<str:action>/", mv.ManagerPushView.as_view(), name="agency-manager-push-action"),
    re_path(r"^manager/.*$", mv.ManagerForbiddenView.as_view(), name="agency-manager-forbidden"),
]
