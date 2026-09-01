from django.urls import include, path
from rest_framework.routers import SimpleRouter

from .views.auth import StaffLoginView, StaffMeView, StaffRefreshView
from .views.branding import SiteConfigView
from .views.catalog import (
    BankCardViewSet,
    PageViewSet,
    PermissionListViewSet,
    PlanAdminViewSet,
    RoleViewSet,
    StaffViewSet,
    ThemeViewSet,
)
from .views.finance import AccountingView, TransactionViewSet
from .views.integrations import (
    EmailStatusView,
    PanelConfigView,
    PanelGroupsView,
    PanelTestView,
    TelegramConfigView,
)
from .views.monitoring import BackupViewSet, HealthView, MonitoringView, ResourcesView
from .views.notifications import NotificationViewSet
from .views.ops import DashboardView, ServiceListViewSet, TelegramStatsView
from .views.system import SystemView
from .views.users import UserAdminViewSet

router = SimpleRouter()
router.register("users", UserAdminViewSet, basename="admin-users")
router.register("plans", PlanAdminViewSet, basename="admin-plans")
router.register("cards", BankCardViewSet, basename="admin-cards")
router.register("pages", PageViewSet, basename="admin-pages")
router.register("themes", ThemeViewSet, basename="admin-themes")
router.register("roles", RoleViewSet, basename="admin-roles")
router.register("permissions", PermissionListViewSet, basename="admin-permissions")
router.register("staff", StaffViewSet, basename="admin-staff")
router.register("transactions", TransactionViewSet, basename="admin-transactions")
router.register("notifications", NotificationViewSet, basename="admin-notifications")
router.register("services", ServiceListViewSet, basename="admin-services")
router.register("backups", BackupViewSet, basename="admin-backups")

urlpatterns = [
    path("auth/login/", StaffLoginView.as_view(), name="admin-login"),
    path("auth/refresh/", StaffRefreshView.as_view(), name="admin-refresh"),
    path("auth/me/", StaffMeView.as_view(), name="admin-me"),
    path("accounting/", AccountingView.as_view(), name="admin-accounting"),
    path("branding/", SiteConfigView.as_view(), name="admin-branding"),
    path("dashboard/", DashboardView.as_view(), name="admin-dashboard"),
    path("telegram-stats/", TelegramStatsView.as_view(), name="admin-telegram-stats"),
    path("health/", HealthView.as_view(), name="admin-health"),
    path("resources/", ResourcesView.as_view(), name="admin-resources"),
    path("monitoring/", MonitoringView.as_view(), name="admin-monitoring"),
    path("system/", SystemView.as_view(), name="admin-system"),
    path("integrations/panel/", PanelConfigView.as_view(), name="admin-panel-config"),
    path("integrations/panel/test/", PanelTestView.as_view(), name="admin-panel-test"),
    path("integrations/panel/groups/", PanelGroupsView.as_view(), name="admin-panel-groups"),
    path("integrations/telegram/", TelegramConfigView.as_view(), name="admin-telegram-config"),
    path("integrations/email/", EmailStatusView.as_view(), name="admin-email-status"),
    path("", include(router.urls)),
]
