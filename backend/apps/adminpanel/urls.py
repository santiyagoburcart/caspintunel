from django.urls import include, path
from rest_framework.routers import SimpleRouter

from .views.apps import AppReleaseDetailView, AppReleaseDownloadView, AppReleaseListView, ShortcutQrView
from .views.auth import StaffLoginView, StaffMeView, StaffRefreshView
from .views.branding import QrPreviewView, SiteConfigView
from .views.docs import DocsListView, DocsPageView
from .views.agency import (AgencyAdminActionView, AgencyAdminDetailView, AgencyAdminListView, AgencyDashboardView,
                           AgencyGroupsView, AgencyLedgerExportView, AgencyLedgerOverviewView, AgencyLedgerView,
                           AgencyLedgerVoidView, AgencySettingsView, AgencySyncLogsView, AgencySyncNowView)
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
    PaymentDecisionView,
    PendingPaymentsView,
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
from .views.monitoring import BackupViewSet, HealthView, MonitoringView, ResourcesView
from .views.notifications import NotificationViewSet
from .views.ops import DashboardView, ServiceListViewSet, TelegramStatsView
from .views.system import SettingsView, SystemView
from .views.users import DeletedUserArchiveViewSet, UserAdminViewSet

router = SimpleRouter()
router.register("users", UserAdminViewSet, basename="admin-users")
router.register("deleted-users", DeletedUserArchiveViewSet, basename="admin-deleted-users")
router.register("plans", PlanAdminViewSet, basename="admin-plans")
router.register("cards", BankCardViewSet, basename="admin-cards")
router.register("pages", PageViewSet, basename="admin-pages")
router.register("themes", ThemeViewSet, basename="admin-themes")
router.register("roles", RoleViewSet, basename="admin-roles")
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
    path("auth/me/", StaffMeView.as_view(), name="admin-me"),
    path("accounting/", AccountingView.as_view(), name="admin-accounting"),
    path("payments/pending/", PendingPaymentsView.as_view(), name="admin-payments-pending"),
    path("payments/<int:pk>/<str:action>/", PaymentDecisionView.as_view(), name="admin-payment-decision"),
    path("branding/", SiteConfigView.as_view(), name="admin-branding"),
    path("branding/qr-preview/", QrPreviewView.as_view(), name="admin-branding-qr-preview"),
    path("agency/", AgencyDashboardView.as_view(), name="admin-agency"),
    path("agency/admins/", AgencyAdminListView.as_view(), name="admin-agency-admins"),
    path("agency/admins/<str:username>/<str:action>/", AgencyAdminActionView.as_view(), name="admin-agency-action"),
    path("agency/admins/<str:username>/", AgencyAdminDetailView.as_view(), name="admin-agency-admin"),
    path("agency/sync-now/", AgencySyncNowView.as_view(), name="admin-agency-sync-now"),
    path("agency/groups/", AgencyGroupsView.as_view(), name="admin-agency-groups"),
    path("agency/groups/<int:group_id>/", AgencyGroupsView.as_view(), name="admin-agency-group"),
    path("agency/sync-logs/", AgencySyncLogsView.as_view(), name="admin-agency-sync-logs"),
    path("agency/settings/", AgencySettingsView.as_view(), name="admin-agency-settings"),
    path("agency/ledger/", AgencyLedgerOverviewView.as_view(), name="admin-agency-ledger"),
    path("agency/ledger/entries/<int:entry_id>/void/", AgencyLedgerVoidView.as_view(), name="admin-agency-ledger-void"),
    path("agency/ledger/<str:username>/export.csv", AgencyLedgerExportView.as_view(), name="admin-agency-ledger-export"),
    path("agency/ledger/<str:username>/<str:what>/", AgencyLedgerView.as_view(), name="admin-agency-ledger-add"),
    path("agency/ledger/<str:username>/", AgencyLedgerView.as_view(), name="admin-agency-ledger-admin"),
    path("docs/", DocsListView.as_view(), name="admin-docs"),
    path("docs/<str:slug>/", DocsPageView.as_view(), name="admin-docs-page"),
    path("dashboard/", DashboardView.as_view(), name="admin-dashboard"),
    path("telegram-stats/", TelegramStatsView.as_view(), name="admin-telegram-stats"),
    path("health/", HealthView.as_view(), name="admin-health"),
    path("resources/", ResourcesView.as_view(), name="admin-resources"),
    path("monitoring/", MonitoringView.as_view(), name="admin-monitoring"),
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
