"""Phase 1 Release C: last backfill before `tenant` becomes NOT NULL on the tenant tables. Rows created by data
migrations (historical models have no pre_save fill) or by code before Release B still lack a tenant — they get the
default tenant here. Same idempotent backfill as 0002 / 0003; every app's NOT NULL migration depends on this one."""
from django.db import migrations


def forward(apps, schema_editor):
    from apps.tenancy.backfill import backfill

    backfill(apps)


class Migration(migrations.Migration):
    dependencies = [
        ("tenancy", "0003_backfill_release_b"),
        ("accounts", "0017_alter_user_managers_user_user_tenant_username_and_more"),
        ("panel", "0005_service_tenant"),
        ("plans", "0007_plan_tenant"),
        ("orders", "0011_manualinvoice_tenant_order_tenant_and_more"),
        ("payments_sms", "0017_bankcard_tenant_payment_tenant_smsappdevice_tenant_and_more"),
        ("notifications", "0006_notification_tenant_notificationdelivery_tenant_and_more"),
        ("telegram", "0004_requiredchannel_tenant_telegramstats_tenant"),
        ("settings_app", "0017_page_page_tenant_slug"),
        ("tickets", "0004_cannedreply_tenant_ticket_tenant_and_more"),
        ("crm", "0007_discountcode_crm_discount_code_tenant_code_and_more"),
    ]

    operations = [migrations.RunPython(forward, migrations.RunPython.noop)]
