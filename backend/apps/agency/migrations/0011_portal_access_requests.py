from django.db import migrations, models

GM_REQ = ("agency.gm.request_volume", "Group manager: request volume for group admins", "مدیر گروه: درخواست شارژ برای ادمین‌های گروه")


def grant(apps, schema_editor):
    """v1.35: every group-manager role may request volume once (narrowed later on the Roles page)."""
    Permission = apps.get_model("accounts", "Permission")
    Role = apps.get_model("accounts", "Role")
    p, _ = Permission.objects.update_or_create(code=GM_REQ[0], defaults={"name": GM_REQ[1], "name_fa": GM_REQ[2]})
    for role in Role.objects.filter(permissions__code="agency.group_manager").distinct():
        role.permissions.add(p)


class Migration(migrations.Migration):

    dependencies = [
        ("agency", "0010_invoices_payments"),
    ]

    operations = [
        migrations.CreateModel(
            name="AgencyAdminSetting",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("username", models.CharField(max_length=255, unique=True)),
                ("portal_login", models.CharField(choices=[("auto", "Policy"), ("on", "Allowed"), ("off", "Blocked")],
                                                  default="auto", max_length=4)),
                ("updated_by", models.CharField(blank=True, default="", max_length=150)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"db_table": "agency_admin_setting"},
        ),
        migrations.RunPython(grant, migrations.RunPython.noop),
    ]
