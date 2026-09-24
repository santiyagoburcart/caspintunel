"""Add the "services.manage" permission (status change / reset / revoke /
manual creation on the new admin Services page)."""
from django.db import migrations


def forward(apps, schema_editor):
    Permission = apps.get_model("accounts", "Permission")
    Permission.objects.update_or_create(
        code="services.manage",
        defaults={"name": "Manage sold services (status, reset, revoke, create)"},
    )


def backward(apps, schema_editor):
    Permission = apps.get_model("accounts", "Permission")
    Permission.objects.filter(code="services.manage").delete()


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0002_user_admin_note"),
    ]

    operations = [
        migrations.RunPython(forward, backward),
    ]
