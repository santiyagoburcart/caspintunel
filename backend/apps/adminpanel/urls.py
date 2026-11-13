from django.urls import include, path
from rest_framework.routers import SimpleRouter

from .views.apps import AppReleaseDetailView, AppReleaseDownloadView, AppReleaseListView, ShortcutQrView
from .views.auth import StaffLoginView, StaffLogoutView, StaffMeView, StaffRefreshView
from .views.branding import QrPreviewView, SiteConfigView
from .views.docs import DocsListView, DocsPageView
from .views.domain import (AccessDetectView, AccessDns01View, AccessSettingsView, AccessSwitchView, DomainRollbackView,
                           DomainSettingsView, DomainStartView, DomainStepView, DomainTokenView, DomainView)
from .views.agency_managers import (AgencyApprovalActionView, AgencyApprovalsBadgeView, AgencyApprovalsBulkView,
                                     AgencyApprovalsView, AgencyGroupActivityView, AgencyGroupLedgerView,
                                     AgencyManagerOptionsView, AgencyManagerPasswordView, AgencyManagersView)
from .views.agency import (AgencyLimitHistoryView, AgencyAdminActionView, AgencyAdminDetailView, AgencyAdminListView, AgencyDashboardView,
                           AgencyGroupsView, AgencyLedgerExportView, AgencyLedgerOverviewView, AgencyLedgerView,
                           AgencyLedgerVoidView, AgencySettingsView, AgencySyncLogsView, AgencySyncNowView, PathsView,
                           AgencyPortalLinkView, AgencySetLimitPreviewView, AgencyLedgerReportView,
                           AgencyPanelAdminCreateView, AgencyPanelAdminOptionsView, AgencyPanelAdminView, AgencyStoreView,
                           AgencyStoreBotCheckView, AgencyStoreBotView, AgencyStoreCeilingView, AgencyStoreOwnerView, AgencyStoreThemeView,
                           AgencyStoreFailedOrdersView, AgencyStoreFailedOrderRetryView,
                           AgencyStoreDomainCheckView, AgencyStoreDomainsView,
                           AgencyStoreDomainView, AgencyHistoryView)
from .views.wireguard import WireguardLocationViewSet, WireguardTemplateView
from .views.store_import import (AgencyStoreImportReportView, AgencyStoreImportRunView, AgencyStoreImportsView,
                                 AgencyStoreImportUndoView, AgencyStoreImportView)
from .views.stores_extra import (AgencyStoreExportLinkView, AgencyStoreExportView, AgencyStoreFeeView,
                                 StoreExportLinkView, StoreExportView)
from .views.catalog import (
    BankCardViewSet,
    PageViewSet,
    PermissionListViewSet,
    PlanAdminViewSet,
    RoleViewSet,
    SmsAppDeviceViewSet,
    SmsSourceViewSet,
    StaffViewSet,
    ThemeViewSet,
)
from .views.email import EmailSettingsView, EmailTestView
from .views.finance import (
    AccountingView,
    BluAttachView,
    BluCandidatesView,
    BluTransactionListView,
    BluUnlinkView,
    PaymentDecisionView,
    PaymentReceiptInfoView,
    PendingPaymentsView,
    FailedOrdersView,
    FailedOrderRetryView,
    SmsLogViewSet,
    TransactionViewSet,
)
from .views.integrations import (
    BackupTestView,
    BotStatsView,
    PanelAdminViewSet,
    PanelConfigView,
    PanelGroupsView,
    PanelTestView,
    RequiredChannelViewSet,
    TelegramConfigView,
)
from .views.monitoring import BackupViewSet, HealthView, MonitoringView, ResourcesView, SslCertificatesView
from .views.push import StaffPrefsView, StaffPushView
from .views.manual_invoices import ManualInvoiceCancelView, UserManualInvoiceOptionsView, UserManualInvoicesView
from .views.agency_billing import (AgencyInvoicesView, AgencyInvoiceVoidView, AgencyInvoiceOutsideView, AgencyGroupDebtView, AgencyPaymentActionView,
                                   AgencyPaymentReceiptView, AgencyPaymentsBadgeView, AgencyPaymentsView, AgencyPortalAccessView,
                                   AgencySettlementView)
from .views.notifications import NotificationViewSet
from .views.ops import DashboardView, ServiceListViewSet, TelegramStatsView
from .views.system import SettingsView, SystemView
from .views.users import DeletedUserArchiveViewSet, UserAdminViewSet
from .views.discounts import DiscountCodeViewSet

router = SimpleRouter()
router.register("users", UserAdminViewSet, basename="admin-users")
router.register("deleted-users", DeletedUserArchiveViewSet, basename="admin-deleted-users")
router.register("plans", PlanAdminViewSet, basename="admin-plans")
router.register("wireguard/locations", WireguardLocationViewSet, basename="admin-wireguard-locations")   # v1.55
router.register("cards", BankCardViewSet, basename="admin-cards")
router.register("pages", PageViewSet, basename="admin-pages")
router.register("themes", ThemeViewSet, basename="admin-themes")
router.register("roles", RoleViewSet, basename="admin-roles")
router.register("discounts", DiscountCodeViewSet, basename="admin-discounts")
router.register("permissions", PermissionListViewSet, basename="admin-permissions")
router.register("staff", StaffViewSet, basename="admin-staff")
router.register("transactions", TransactionViewSet, basename="admin-transactions")
router.register("sms-log", SmsLogViewSet, basename="admin-sms-log")
router.register("notifications", NotificationViewSet, basename="admin-notifications")
router.register("services", ServiceListViewSet, basename="admin-services")
router.register("backups", BackupViewSet, basename="admin-backups")
router.register("panels", PanelAdminViewSet, basename="admin-panels")
router.register("channels", RequiredChannelViewSet, basename="admin-channels")
router.register("sms-devices", SmsAppDeviceViewSet, basename="admin-sms-devices")
router.register("sms-sources", SmsSourceViewSet, basename="admin-sms-sources")

urlpatterns = [
    path("auth/login/", StaffLoginView.as_view(), name="admin-login"),
    path("auth/refresh/", StaffRefreshView.as_view(), name="admin-refresh"),
    path("auth/logout/", StaffLogoutView.as_view(), name="admin-logout"),
    path("auth/me/", StaffMeView.as_view(), name="admin-me"),
    path("auth/me/prefs/", StaffPrefsView.as_view(), name="admin-me-prefs"),
    path("push/", StaffPushView.as_view(), name="admin-push"),
    path("push/<str:action>/", StaffPushView.as_view(), name="admin-push-action"),
    path("accounting/", AccountingView.as_view(), name="admin-accounting"),
    path("payments/pending/", PendingPaymentsView.as_view(), name="admin-payments-pending"),
    path("wireguard/template/", WireguardTemplateView.as_view(), name="admin-wireguard-template"),     # v1.55.2
    path("orders/provision-failed/", FailedOrdersView.as_view(), name="admin-orders-provision-failed"),
    # v1.53 (Phase 10): the store's own backups (the one-time download is /api/v1/exports/download/…, config/urls.py)
    path("store-export/", StoreExportView.as_view(), name="admin-store-export"),
    path("store-export/<int:pk>/link/", StoreExportLinkView.as_view(), name="admin-store-export-link"),
    path("orders/provision-failed/<int:pk>/retry/", FailedOrderRetryView.as_view(), name="admin-orders-provision-retry"),
    path("payments/blu-transactions/", BluTransactionListView.as_view(), name="admin-blu-transactions"),
    path("payments/blu-transactions/<int:pk>/attach/", BluAttachView.as_view(), name="admin-blu-attach"),
    path("payments/blu-transactions/<int:pk>/candidates/", BluCandidatesView.as_view(), name="admin-blu-candidates"),
    path("payments/blu-transactions/<int:pk>/unlink/", BluUnlinkView.as_view(), name="admin-blu-unlink"),
    path("payments/<int:pk>/receipt-info/", PaymentReceiptInfoView.as_view(), name="admin-payment-receipt-info"),
    path("payments/<int:pk>/<str:action>/", PaymentDecisionView.as_view(), name="admin-payment-decision"),
    path("branding/", SiteConfigView.as_view(), name="admin-branding"),
    path("branding/qr-preview/", QrPreviewView.as_view(), name="admin-branding-qr-preview"),
    path("paths/", PathsView.as_view(), name="admin-paths"),
    path("domain/", DomainView.as_view(), name="admin-domain"),
    path("domain/token/", DomainTokenView.as_view(), name="admin-domain-token"),
    path("domain/token/test/", DomainTokenView.as_view(), {"test": True}, name="admin-domain-token-test"),
    path("domain/settings/", DomainSettingsView.as_view(), name="admin-domain-settings"),
    path("domain/start/", DomainStartView.as_view(), name="admin-domain-start"),
    path("domain/rollback/", DomainRollbackView.as_view(), name="admin-domain-rollback"),
    path("domain/access/", AccessSwitchView.as_view(), name="admin-access-switch"),
    path("domain/access/back/", AccessSwitchView.as_view(), {"back": True}, name="admin-access-back"),
    path("domain/access/settings/", AccessSettingsView.as_view(), name="admin-access-settings"),
    path("domain/access/detect/", AccessDetectView.as_view(), name="admin-access-detect"),
    path("domain/access/dns01/", AccessDns01View.as_view(), name="admin-access-dns01"),
    path("domain/<int:pk>/<str:step>/", DomainStepView.as_view(), name="admin-domain-step"),
    path("agency/", AgencyDashboardView.as_view(), name="admin-agency"),
    path("agency/admins/", AgencyAdminListView.as_view(), name="admin-agency-admins"),
    path("agency/panel-admins/options/", AgencyPanelAdminOptionsView.as_view(), name="admin-agency-panel-admin-options"),
    path("agency/panel-admins/", AgencyPanelAdminCreateView.as_view(), name="admin-agency-panel-admin-create"),
    path("agency/history/", AgencyHistoryView.as_view(), name="admin-agency-history"),        # v1.54 «تاریخچه»
    path("agency/panel-admins/<str:username>/store/", AgencyStoreView.as_view(), name="admin-agency-store"),
    path("agency/panel-admins/<str:username>/store/domains/", AgencyStoreDomainsView.as_view(), name="admin-agency-store-domains"),
    path("agency/panel-admins/<str:username>/store/bot/", AgencyStoreBotView.as_view(), name="admin-agency-store-bot"),
    path("agency/panel-admins/<str:username>/store/ceiling/", AgencyStoreCeilingView.as_view(), name="admin-agency-store-ceiling"),
    path("agency/panel-admins/<str:username>/store/theme/", AgencyStoreThemeView.as_view(), name="admin-agency-store-theme"),
    path("agency/panel-admins/<str:username>/store/owner/", AgencyStoreOwnerView.as_view(), name="admin-agency-store-owner"),
    # v1.53: store exports (Phase 10) + the monthly store fee (Phase 12) on «فروشگاه»
    path("agency/panel-admins/<str:username>/store/exports/", AgencyStoreExportView.as_view(), name="admin-agency-store-exports"),
    path("agency/panel-admins/<str:username>/store/exports/<int:pk>/link/", AgencyStoreExportLinkView.as_view(),
         name="admin-agency-store-export-link"),
    path("agency/panel-admins/<str:username>/store/fee/", AgencyStoreFeeView.as_view(), name="admin-agency-store-fee"),
    # v1.56: «ورود داده از ربات قبلی» (tenancy/importers) — our staff only
    path("agency/panel-admins/<str:username>/store/imports/", AgencyStoreImportsView.as_view(), name="admin-agency-store-imports"),
    path("agency/panel-admins/<str:username>/store/imports/<int:pk>/", AgencyStoreImportView.as_view(), name="admin-agency-store-import"),
    path("agency/panel-admins/<str:username>/store/imports/<int:pk>/run/", AgencyStoreImportRunView.as_view(),
         name="admin-agency-store-import-run"),
    path("agency/panel-admins/<str:username>/store/imports/<int:pk>/undo/", AgencyStoreImportUndoView.as_view(),
         name="admin-agency-store-import-undo"),
    path("agency/panel-admins/<str:username>/store/imports/<int:pk>/report.csv", AgencyStoreImportReportView.as_view(),
         name="admin-agency-store-import-report"),
    path("agency/panel-admins/<str:username>/store/failed-orders/", AgencyStoreFailedOrdersView.as_view(),
         name="admin-agency-store-failed-orders"),
    path("agency/panel-admins/<str:username>/store/failed-orders/<int:pk>/retry/", AgencyStoreFailedOrderRetryView.as_view(),
         name="admin-agency-store-failed-order-retry"),
    path("agency/panel-admins/<str:username>/store/bot/check/", AgencyStoreBotCheckView.as_view(),
         name="admin-agency-store-bot-check"),
    path("agency/panel-admins/<str:username>/store/domains/<int:pk>/", AgencyStoreDomainView.as_view(), name="admin-agency-store-domain"),
    path("agency/panel-admins/<str:username>/store/domains/<int:pk>/check/", AgencyStoreDomainCheckView.as_view(),
         name="admin-agency-store-domain-check"),
    path("agency/panel-admins/<str:username>/", AgencyPanelAdminView.as_view(), name="admin-agency-panel-admin"),
    path("agency/admins/<str:username>/limit-history/", AgencyLimitHistoryView.as_view(), name="admin-agency-limit-history"),
    path("agency/admins/<str:username>/set-limit/preview/", AgencySetLimitPreviewView.as_view(), name="admin-agency-limit-preview"),
    path("agency/admins/<str:username>/<str:action>/", AgencyAdminActionView.as_view(), name="admin-agency-action"),
    path("agency/portal-link/", AgencyPortalLinkView.as_view(), name="admin-agency-portal-link"),
    path("agency/portal-link/qr.png", AgencyPortalLinkView.as_view(), {"fmt": "png"}, name="admin-agency-portal-qr"),
    path("agency/admins/<str:username>/", AgencyAdminDetailView.as_view(), name="admin-agency-admin"),
    path("agency/sync-now/", AgencySyncNowView.as_view(), name="admin-agency-sync-now"),
    path("agency/groups/", AgencyGroupsView.as_view(), name="admin-agency-groups"),
    path("agency/groups/<int:group_id>/", AgencyGroupsView.as_view(), name="admin-agency-group"),
    path("agency/groups/<int:group_id>/debt/", AgencyGroupDebtView.as_view(), name="admin-agency-group-debt"),
    path("agency/groups/<int:group_id>/activity/", AgencyGroupActivityView.as_view(), name="admin-agency-group-activity"),
    path("agency/managers/", AgencyManagersView.as_view(), name="admin-agency-managers"),
    path("agency/managers/options/", AgencyManagerOptionsView.as_view(), name="admin-agency-manager-options"),
    path("agency/managers/<int:manager_id>/", AgencyManagersView.as_view(), name="admin-agency-manager"),
    path("agency/managers/<int:manager_id>/password/", AgencyManagerPasswordView.as_view(), name="admin-agency-manager-password"),
    path("users/<int:user_id>/manual-invoices/", UserManualInvoicesView.as_view(), name="admin-user-manual-invoices"),
    path("users/<int:user_id>/manual-invoices/options/", UserManualInvoiceOptionsView.as_view(), name="admin-user-manual-invoice-options"),
    path("manual-invoices/<int:pk>/cancel/", ManualInvoiceCancelView.as_view(), name="admin-manual-invoice-cancel"),
    path("agency/invoices/", AgencyInvoicesView.as_view(), name="admin-agency-invoices"),
    path("agency/portal-access/<str:username>/", AgencyPortalAccessView.as_view(), name="admin-agency-portal-access"),
    path("agency/invoices/settlement/", AgencySettlementView.as_view(), name="admin-agency-settlement"),
    path("agency/invoices/<int:pk>/void/", AgencyInvoiceVoidView.as_view(), name="admin-agency-invoice-void"),
    path("agency/invoices/<int:pk>/settle-outside/", AgencyInvoiceOutsideView.as_view(), name="admin-agency-invoice-outside"),
    path("agency/payments/", AgencyPaymentsView.as_view(), name="admin-agency-payments"),
    path("agency/payments/badge/", AgencyPaymentsBadgeView.as_view(), name="admin-agency-payments-badge"),
    path("agency/payments/<int:pk>/receipt/", AgencyPaymentReceiptView.as_view(), name="admin-agency-payment-receipt"),
    path("agency/payments/<int:pk>/<str:action>/", AgencyPaymentActionView.as_view(), name="admin-agency-payment-action"),
    path("agency/approvals/", AgencyApprovalsView.as_view(), name="admin-agency-approvals"),
    path("agency/approvals/badge/", AgencyApprovalsBadgeView.as_view(), name="admin-agency-approvals-badge"),
    path("agency/approvals/bulk-approve/", AgencyApprovalsBulkView.as_view(), name="admin-agency-approvals-bulk"),
    path("agency/approvals/<int:request_id>/<str:action>/", AgencyApprovalActionView.as_view(), name="admin-agency-approval-action"),
    path("agency/sync-logs/", AgencySyncLogsView.as_view(), name="admin-agency-sync-logs"),
    path("agency/settings/", AgencySettingsView.as_view(), name="admin-agency-settings"),
    path("agency/ledger/", AgencyLedgerOverviewView.as_view(), name="admin-agency-ledger"),
    path("agency/ledger/entries/<int:entry_id>/void/", AgencyLedgerVoidView.as_view(), name="admin-agency-ledger-void"),
    path("agency/ledger/groups/", AgencyGroupLedgerView.as_view(), name="admin-agency-ledger-groups"),
    path("agency/ledger/groups/<int:group_id>/statement/", AgencyGroupLedgerView.as_view(), name="admin-agency-ledger-group"),
    path("agency/ledger/report/<str:what>/", AgencyLedgerReportView.as_view(), name="admin-agency-ledger-report"),
    path("agency/ledger/report/<str:what>/<int:jy>/<int:jm>/", AgencyLedgerReportView.as_view(), name="admin-agency-ledger-month"),
    path("agency/ledger/<str:username>/export.csv", AgencyLedgerExportView.as_view(), name="admin-agency-ledger-export"),
    path("agency/ledger/<str:username>/<str:what>/", AgencyLedgerView.as_view(), name="admin-agency-ledger-add"),
    path("agency/ledger/<str:username>/", AgencyLedgerView.as_view(), name="admin-agency-ledger-admin"),
    path("tickets/", include("apps.tickets.admin_urls")),
    path("crm/", include("apps.crm.urls")),
    path("docs/", DocsListView.as_view(), name="admin-docs"),
    path("docs/<str:slug>/", DocsPageView.as_view(), name="admin-docs-page"),
    path("dashboard/", DashboardView.as_view(), name="admin-dashboard"),
    path("telegram-stats/", TelegramStatsView.as_view(), name="admin-telegram-stats"),
    path("health/", HealthView.as_view(), name="admin-health"),
    path("resources/", ResourcesView.as_view(), name="admin-resources"),
    path("monitoring/", MonitoringView.as_view(), name="admin-monitoring"),
    path("monitoring/ssl/", SslCertificatesView.as_view(), name="admin-monitoring-ssl"),       # v1.57
    path("system/", SystemView.as_view(), name="admin-system"),
    path("settings/", SettingsView.as_view(), name="admin-settings"),
    path("integrations/panel/", PanelConfigView.as_view(), name="admin-panel-config"),
    path("integrations/panel/test/", PanelTestView.as_view(), name="admin-panel-test"),
    path("integrations/panel/groups/", PanelGroupsView.as_view(), name="admin-panel-groups"),
    path("integrations/telegram/", TelegramConfigView.as_view(), name="admin-telegram-config"),
    path("bots/stats/", BotStatsView.as_view(), name="admin-bots-stats"),
    path("bots/backup-test/", BackupTestView.as_view(), name="admin-bots-backup-test"),
    path("email/", EmailSettingsView.as_view(), name="admin-email-settings"),
    path("email/test/", EmailTestView.as_view(), name="admin-email-test"),
    path("apps/", AppReleaseListView.as_view(), name="admin-apps"),
    path("apps/ios/qr/", ShortcutQrView.as_view(), name="admin-shortcut-qr"),
    path("apps/<str:platform>/", AppReleaseDetailView.as_view(), name="admin-app-release"),
    path("apps/<str:platform>/download/", AppReleaseDownloadView.as_view(), name="admin-app-download"),
    path("", include(router.urls)),
]
