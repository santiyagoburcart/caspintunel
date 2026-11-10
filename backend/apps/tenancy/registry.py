"""Every model of the project, classified (docs/multi-tenant.md §3–4). tests/test_registry.py fails when a model is
missing from here — a new table must be decided as tenant data or platform data on purpose.

TENANT    — customer-facing data of one store: has `tenant`, filled with the default tenant (NOT NULL from Release C).
NULLABLE  — `tenant` stays nullable for good: NULL = platform (our staff / roles / audit / push of staff and resellers,
            built-in themes). The backfill rule per model is in BACKFILL_FILTER.
PLATFORM  — ours only, no `tenant` (panels, agency ledger / invoices / payments, Blu, ops, settings, our bots).
"""

TENANT = [
    "accounts.User", "accounts.DeletedUserArchive",
    "panel.Service", "plans.Plan",
    "orders.Order", "orders.ScheduledRenewal", "orders.ManualInvoice",
    "payments_sms.Payment", "payments_sms.BankCard", "payments_sms.SmsSource", "payments_sms.SmsAppDevice",
    "payments_sms.SmsMessage",
    "notifications.Notification", "notifications.NotificationDelivery",
    "telegram.RequiredChannel", "telegram.TelegramStats",
    "settings_app.Page", "settings_app.TenantBranding", "settings_app.TenantSetting",
    "tickets.TicketTopic", "tickets.Ticket", "tickets.TicketMessage", "tickets.TicketAttachment", "tickets.TicketEvent",
    "tickets.CannedReply",
    "crm.Tag", "crm.CustomerProfile", "crm.CustomerNote", "crm.CaseReason", "crm.FollowUpCase", "crm.MessageTemplate",
    "crm.CrmEvent", "crm.WarningRule", "crm.ServiceWarning", "crm.ServiceEndMark", "crm.DiscountCode",
    "tenancy.TenantExport",          # v1.53: a store's own backups (tenancy/export.py)
]

NULLABLE = [
    "accounts.Staff", "accounts.Role", "common.AuditLog", "notifications.PushSubscription", "settings_app.Theme",
]

# which existing rows of a NULLABLE model belong to the default store (the rest stay platform = NULL)
BACKFILL_FILTER = {
    "notifications.PushSubscription": {"user__isnull": False},      # customers' browsers; staff / reseller rows stay NULL
}

PLATFORM = [
    "accounts.Permission", "accounts.StaffRevokedToken",
    "panel.Panel",
    "payments_sms.BluTransaction", "payments_sms.BluCollector",
    "telegram.TelegramConfig",
    "settings_app.Setting", "settings_app.SiteConfig", "settings_app.AppRelease", "settings_app.EmailSettings",
    "settings_app.DomainConfig", "settings_app.DomainChange",
    "ops.BackupLog", "ops.CleanupRun", "ops.HealthCheck", "ops.ResourceStat",
    "agency.PanelAdmin", "agency.AdminLimit", "agency.SyncLog", "agency.UserTrafficSnapshot", "agency.AdminGroup",
    "agency.ResellerSession", "agency.AdminPrice", "agency.LedgerEntry", "agency.AdminLimitChange", "agency.GroupManager",
    "agency.GroupManagerAssignment", "agency.ManagerSession", "agency.VolumeRequest", "agency.AgencyInvoice",
    "agency.AgencyPayment", "agency.AgencyPaymentItem", "agency.AgencyInvoiceAllocation", "agency.AgencyNotice",
    "agency.AgencyAdminSetting",
    "tenancy.Tenant", "tenancy.TenantDomain", "tenancy.TenantBot", "tenancy.TenantFee", "tenancy.TenantFeeInvoice",
]

PROJECT_APPS = ("accounts", "adminpanel", "agency", "common", "crm", "notifications", "ops", "orders", "panel",
                "payments_sms", "plans", "settings_app", "telegram", "tickets", "tenancy")
