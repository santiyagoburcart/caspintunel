"""v1.25: group managers sign in to /panel/ as staff accounts with the RBAC role
"Group manager". Adds GroupManager.staff and converts every existing manager into a
staff account with the same username and password hash (both use Django hashers).

A staff username that is already taken is never linked or changed (that would lock a
real operator into a group); such a manager is left unlinked and shown on the
Managers page so staff can pick a new username."""
import django.db.models.deletion
from django.db import migrations, models

GM_PERM = ("agency.group_manager", "Group manager: own groups only (agency admins, volume, accounting)")
GM_ROLE = "Group manager"


def forwards(apps, schema_editor):
    Permission = apps.get_model("accounts", "Permission")
    Role = apps.get_model("accounts", "Role")
    Staff = apps.get_model("accounts", "Staff")
    GroupManager = apps.get_model("agency", "GroupManager")

    perm, _ = Permission.objects.update_or_create(code=GM_PERM[0], defaults={"name": GM_PERM[1]})
    role, _ = Role.objects.get_or_create(name=GM_ROLE, defaults={"description": "Group managers — own agency groups only"})
    role.permissions.set([perm])
    for m in GroupManager.objects.filter(staff__isnull=True):
        if Staff.objects.filter(username__iexact=m.username).exists():
            continue
        s = Staff.objects.create(username=m.username, password_hash=m.password, role=role, is_active=m.is_active,
                                 is_superadmin=False, display_name=(m.display_name or "")[:60],
                                 last_login=m.last_login_at)
        m.staff_id = s.pk
        m.save(update_fields=["staff"])


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0012_staff_display_name"),
        ("agency", "0006_group_managers"),
    ]

    operations = [
        migrations.AddField(
            model_name="groupmanager",
            name="staff",
            field=models.OneToOneField(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                                       related_name="group_manager", to="accounts.staff"),
        ),
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
