"""Phase 1 Release A: the default tenant (our own store, its current domain) and every existing customer-facing row
assigned to it. Idempotent — only rows whose tenant is still NULL are updated (apps/tenancy/backfill.py)."""
from django.db import migrations


def forward(apps, schema_editor):
    from apps.tenancy.backfill import backfill

    backfill(apps)


class Migration(migrations.Migration):
    dependencies = [
        ("tenancy", "0001_initial"),
        ("accounts", "0016_deleteduserarchive_tenant_role_tenant_staff_tenant_and_more"),
        ("common", "0002_auditlog_tenant"),
        ("crm", "0006_casereason_tenant_crmevent_tenant_and_more"),
        ("notifications", "0006_notification_tenant_notificationdelivery_tenant_and_more"),
        ("orders", "0011_manualinvoice_tenant_order_tenant_and_more"),
        ("panel", "0005_service_tenant"),
        ("payments_sms", "0017_bankcard_tenant_payment_tenant_smsappdevice_tenant_and_more"),
        ("plans", "0007_plan_tenant"),
        ("settings_app", "0016_page_tenant_theme_tenant"),
        ("telegram", "0004_requiredchannel_tenant_telegramstats_tenant"),
        ("tickets", "0004_cannedreply_tenant_ticket_tenant_and_more"),
    ]

    operations = [migrations.RunPython(forward, migrations.RunPython.noop)]
