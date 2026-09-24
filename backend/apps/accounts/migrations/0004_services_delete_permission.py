"""Add the "services.delete" permission (permanently remove a sold service
from the admin Services page — separate from services.manage since it's a
destructive, harder-to-reverse action)."""
from django.db import migrations


def forward(apps, schema_editor):
    Permission = apps.get_model("accounts", "Permission")
    Permission.objects.update_or_create(
        code="services.delete",
        defaults={"name": "Delete sold services"},
    )


def backward(apps, schema_editor):
    Permission = apps.get_model("accounts", "Permission")
    Permission.objects.filter(code="services.delete").delete()


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0003_services_manage_permission"),
    ]

    operations = [
        migrations.RunPython(forward, backward),
    ]
