from django.db import migrations

PERM = ("agency.gm.full_stats", "Group manager: view full reseller stats", "مدیر گروه: مشاهده آمار کامل نمایندگان")


def grant(apps, schema_editor):
    """v1.36: every group-manager role sees the full reseller stats by default (narrowed on the Roles page)."""
    Permission = apps.get_model("accounts", "Permission")
    Role = apps.get_model("accounts", "Role")
    p, _ = Permission.objects.update_or_create(code=PERM[0], defaults={"name": PERM[1], "name_fa": PERM[2]})
    for role in Role.objects.filter(permissions__code="agency.group_manager").distinct():
        role.permissions.add(p)


class Migration(migrations.Migration):
    dependencies = [("agency", "0012_invoice_allocations"), ("accounts", "0015_notify_prefs")]

    operations = [migrations.RunPython(grant, migrations.RunPython.noop)]
