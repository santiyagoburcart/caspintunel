"""Phase 1 Release B: rows created between Release A and B (code did not set tenant yet) get the default tenant before
the scoped managers start filtering on it. Same idempotent backfill as 0002."""
from django.db import migrations


def forward(apps, schema_editor):
    from apps.tenancy.backfill import backfill

    backfill(apps)


class Migration(migrations.Migration):
    dependencies = [
        ("tenancy", "0002_default_tenant_backfill"),
        ("accounts", "0017_alter_user_managers_user_user_tenant_username_and_more"),
        ("crm", "0007_discountcode_crm_discount_code_tenant_code_and_more"),
        ("settings_app", "0017_page_page_tenant_slug"),
    ]

    operations = [migrations.RunPython(forward, migrations.RunPython.noop)]
